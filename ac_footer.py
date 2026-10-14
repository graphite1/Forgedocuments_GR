"""AC fixed footer geometry, kept separate from the shared renderer.

The source PDF cannot yet be materialized in this cloud. These visible bounds
come from the user's original-image review, not a completed local overlay.
"""
from copy import deepcopy

ADDRESS = '愛知県豊明市栄町神田182'
REVISION = 1
LEGACY_ADDRESS_BOX = [62, 1165, 900, 46]
LEGACY_COMPANY_BOX = [62, 1100, 900, 60]


def fixed_address():
    return {'id':'company_address', 'text':ADDRESS, 'box':[210,1104,580,34],
            'font':24, 'min_font':24, 'align':'justify', 'wrap':False, 'print':True}


def migrate_footer(template):
    """Upgrade known generated defaults; preserve custom/ambiguous settings."""
    t=deepcopy(template)
    if t.get('ac_footer_revision',0)>=REVISION:
        return t
    if any(f['id'] in ('company_address','address') for f in t['fields']):
        return t  # Preserve historical fields/records; do not reclassify data.
    address=next((i for i in t['fixed_texts'] if i.get('id')=='company_address' or i.get('value_key')=='company_address'),None)
    if address is None:
        return t
    value=t.get(address['value_key'],'') if 'value_key' in address else address.get('text','')
    known_geometry=(address.get('box')==LEGACY_ADDRESS_BOX and address.get('font')==28) or (address.get('box')==fixed_address()['box'] and address.get('font')==24)
    if value!=ADDRESS or not known_geometry or address.get('print',True) is not True:
        return t
    company=next((i for i in t['fixed_texts'] if i.get('id')=='company_name' or i.get('value_key')=='company_name'),None)
    previous=[deepcopy(address)]
    address.clear();address.update(fixed_address())
    if company and company.get('box')==LEGACY_COMPANY_BOX and company.get('font')==40:
        previous.append(deepcopy(company))
        company.update(box=[210,1138,585,60],font=44,align='justify')
    elif company and company.get('box')==[210,1138,585,60] and company.get('font')==44:
        company['align']='justify'
    t['ac_previous_footer']=previous
    t['ac_footer_revision']=REVISION
    t['ac_footer_source']={'library_file_id':'libfile_2212a3b6aaa481919817fbfd71265d13',
        'local_original_pixels_checked':False, 'overlay_verified':False,
        'alignment_status':'candidate_from_original_image_review; local PDF transfer pending'}
    return t


def validate_fixed_footer(template):
    if template.get('ac_footer_revision')!=REVISION:
        return
    addresses=[i for i in template['fixed_texts'] if i.get('id')=='company_address']
    if addresses!=[fixed_address()] or template.get('company_address')!=ADDRESS or any(f['id'] in ('company_address','address') for f in template['fields']):
        raise ValueError('住所は罫線と同じ固定テンプレート要素です。文字・位置・字間を保持してください')
