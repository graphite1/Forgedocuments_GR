"""Create a separate metadata repair of the known raster-derived digit subset.

No automatic Fontspector fixes, outline edits, or additions to the character set.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from reportlab.pdfbase.ttfonts import TTFont,TTFontMaker

SOURCE_SHA256='e65eb34b517e6d4bd97713507800cbef8b24cca0f1fc3c0cfc21b485873c342d'


def table_data(raw):
    result={}
    for i in range(struct.unpack_from('>H',raw,4)[0]):
        tag,checksum,offset,length=struct.unpack_from('>4sIII',raw,12+16*i)
        result[tag.decode('ascii')]=raw[offset:offset+length]
    return result


def repair(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or destination.exists():raise ValueError('Use a new, separate output file')
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:raise ValueError('Unexpected source subset')
    tables=table_data(raw);original=dict(tables)
    n=struct.unpack_from('>H',tables['maxp'],4)[0]
    assert n==15
    metrics=[struct.unpack_from('>Hh',tables['hmtx'],4*i) for i in range(n)]
    assert all(advance==467 for advance,lsb in metrics)
    head=bytearray(tables['head']);struct.pack_into('>I',head,4,round(.1*65536));struct.pack_into('>I',head,8,0);tables['head']=bytes(head)
    # Preserve all advances/side bearings, using the OpenType recommended
    # compressed representation for a monospaced font.
    hhea=bytearray(tables['hhea']);struct.pack_into('>H',hhea,34,3);tables['hhea']=bytes(hhea)
    tables['hmtx']=b''.join(struct.pack('>Hh',*m) for m in metrics[:3])+b''.join(struct.pack('>h',lsb) for advance,lsb in metrics[3:])
    os2=bytearray(tables['OS/2']);os2[32]=2;os2[35]=9
    struct.pack_into('>H',os2,76,0) # All subset ink is at/above the baseline.
    tables['OS/2']=bytes(os2)
    # Declare existing glyph names without adding an outline or Unicode alias.
    names=['space','hyphen','period','zero','one','two','three','four','five','six','seven','eight','nine','B']
    post=bytearray(tables['post'][:32]);struct.pack_into('>I',post,0,0x00020000)
    tables['post']=bytes(post)+struct.pack('>H',n)+struct.pack('>15H',0,*range(258,272))+b''.join(bytes([len(s)])+s.encode('ascii') for s in names)
    name_table=tables['name'];count=struct.unpack_from('>H',name_table,2)[0];start=struct.unpack_from('>H',name_table,4)[0]
    records=b'';strings=b''
    for i in range(count):
        platform,encoding,language,nameid,length,offset=struct.unpack_from('>6H',name_table,6+12*i)
        text=name_table[start+offset:start+offset+length]
        if nameid==5:text='Version 0.100 Prototype; structure checked'.encode('utf-16-be')
        records+=struct.pack('>6H',platform,encoding,language,nameid,len(text),len(strings));strings+=text
    tables['name']=struct.pack('>3H',0,count,6+len(records))+records+strings
    maker=TTFontMaker()
    for tag,data in tables.items():maker.add(tag,data)
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(maker.makeStream())
    result=table_data(destination.read_bytes())
    assert result['glyf']==original['glyf'] and result['loca']==original['loca'] and result['cmap']==original['cmap']
    before=TTFont('BeforeStructureRepair',str(source),validate=1).face
    after=TTFont('AfterStructureRepair',str(destination),validate=1).face
    assert before.charWidths==after.charWidths and before.charToGlyph==after.charToGlyph
    assert hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA256
    record={'source_sha256':SOURCE_SHA256,'output_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'glyph_outline_loca_and_cmap_bytes_identical':True,'decoded_advances_identical':True,
        'source_unchanged':True,'characters_added':0,'outlines_changed':0,
        'changes':['head.fontRevision/name ID5 version consistency','hhea/hmtx lossless monospace metrics compression',
                   'PANOSE Latin Text/Monospaced metadata','usWinDescent=0 matching actual ink bounds',
                   'post format2 names for existing glyphs only']}
    destination.with_suffix('.repair.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();print(json.dumps(repair(args.source,args.destination)))
