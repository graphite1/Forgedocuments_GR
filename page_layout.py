"""Paper placement independent of any form's normalized drawing coordinates."""
import math

MM = 72 / 25.4
PAPERS = {'A4':(210,297),'A3':(297,420),'A5':(148,210),'B4':(257,364),'B5':(182,257),'Letter':(215.9,279.4),'Legal':(215.9,355.6)}


def defaults(template):
    return {'paper':template.get('page_mode','A4'),'orientation':'portrait','rows':1,'columns':1,
            'margin_x_mm':0 if template.get('page_mode')=='A4' else template.get('original_margin_mm',.5),
            'margin_y_mm':0 if template.get('page_mode')=='A4' else template.get('original_margin_mm',.5),
            'gap_x_mm':0,'gap_y_mm':0,'scale':'actual','custom_width_mm':210,'custom_height_mm':297,'align_x':'center','align_y':'center'}


def placements(template):
    """Return paper points and centered frame positions, in row-major order.

    Each position is (left, bottom, scale). 'fit' only shrinks. Empty final
    slots are left blank; a form keeps its own width/height and coordinates.
    """
    cfg=defaults(template);cfg.update(template.get('page_layout',{}))
    fw,fh=float(template['width_mm']),float(template['height_mm'])
    content_h=float(template.get('content_height_mm',fh))
    if not math.isfinite(content_h) or not fh<=content_h<=2000:raise ValueError('出力範囲は外枠以上・2000mm以下で指定してください')
    rows,cols=cfg['rows'],cfg['columns']
    if type(rows) is not int or type(cols) is not int or not 1<=rows<=10 or not 1<=cols<=10:
        raise ValueError('面付けの行数・列数は1〜10の整数で指定してください')
    nums={}
    for key in ('margin_x_mm','margin_y_mm','gap_x_mm','gap_y_mm','custom_width_mm','custom_height_mm'):
        value=cfg[key]
        if isinstance(value,bool):raise ValueError('用紙・余白・間隔はmmの数値で指定してください')
        nums[key]=float(value)
        if not math.isfinite(nums[key]) or nums[key]<0:raise ValueError('用紙・余白・間隔は有限の0以上の値で指定してください')
    mx,my,gx,gy=(nums[k] for k in ('margin_x_mm','margin_y_mm','gap_x_mm','gap_y_mm'))
    paper=cfg['paper']
    if paper=='original':pw,ph=cols*fw+(cols-1)*gx+2*mx,rows*content_h+(rows-1)*gy+2*my
    elif paper=='custom':pw,ph=nums['custom_width_mm'],nums['custom_height_mm']
    elif paper in PAPERS:pw,ph=PAPERS[paper]
    else:raise ValueError('未対応の用紙サイズです')
    if cfg['orientation'] not in ('portrait','landscape'):raise ValueError('用紙の向きが不正です')
    if cfg['orientation']=='landscape' and paper!='original':pw,ph=max(pw,ph),min(pw,ph)
    if not 10<=pw<=2000 or not 10<=ph<=2000:raise ValueError('用紙寸法は10〜2000mmで指定してください')
    cw=(pw-2*mx-(cols-1)*gx)/cols;ch=(ph-2*my-(rows-1)*gy)/rows
    if cw<=0 or ch<=0:raise ValueError('余白・間隔が大きすぎて伝票の配置領域がありません')
    if cfg['scale'] not in ('actual','fit'):raise ValueError('面付け倍率は原寸または縮小で指定してください')
    scale=min(1,cw/fw,ch/content_h) if cfg['scale']=='fit' else 1
    if scale==1 and (fw>cw+1e-7 or content_h>ch+1e-7):
        raise ValueError(f'原寸 {fw:g}×{content_h:g}mm は1枠 {cw:.1f}×{ch:.1f}mmに入りません。用紙・行列・余白を変更するか「枠に合わせて縮小」を選んでください')
    if cfg['align_x'] not in ('center','start') or cfg['align_y'] not in ('center','start'):raise ValueError('枠の配置基準が不正です')
    slots=[]
    for row in range(rows):
        for col in range(cols):
            left=mx+col*(cw+gx)+((cw-fw*scale)/2 if cfg['align_x']=='center' else 0)
            top=my+row*(ch+gy)+((ch-content_h*scale)/2 if cfg['align_y']=='center' else 0)
            slots.append((left*MM,(ph-top-fh*scale)*MM,scale))
    return (pw*MM,ph*MM),slots
