"""Add the background pipeline without changing stored values or custom geometry."""
import copy
from background_assets import missing_background


def migrate_background(template, default):
    if template.get('form_id') != default['form_id']:
        raise ValueError('別の帳票の設定は移行できません')
    expected={f['id'] for f in default['fields']}
    if {f['id'] for f in template['fields']} != expected:
        raise ValueError('生コンの42項目定義を確認してください')
    result=copy.deepcopy(template)
    if result.get('background_revision',0)<1:
        result['render_mode']='background'
        result.setdefault('background',missing_background())
        result['overlay_fixed_text_ids']=copy.deepcopy(default['overlay_fixed_text_ids'])
        result['background_blank_regions_mm']=copy.deepcopy(default['background_blank_regions_mm'])
        result['background_revision']=1
    if result.get('plan_revision',0)<1:
        result['document_purpose']='delivery_plan'
        expected=next(i for i in default['fixed_texts'] if i.get('id')=='copy_notice')
        previous=next((i for i in result['fixed_texts'] if i.get('id')=='copy_notice'),None)
        if previous is None:raise ValueError('識別表示の定義がありません')
        if previous!=expected:
            result['previous_identity_notice']=copy.deepcopy(previous)
            previous.clear();previous.update(copy.deepcopy(expected))
        result['plan_revision']=1
        result['entry_value_label']=default['entry_value_label']
        result['quantity_summary_title']=default['quantity_summary_title']
    if result.get('layout_profile') == 'generated-20261014' and result.get('plan_overlay_revision',0)<1:
        from tomei_profiles import plan_overlays
        result=plan_overlays(result)
    # One-time upgrade of the previous 13-character basic profile. Explicit
    # numeric-only/custom/standard choices and stored input values stay intact.
    from tomei_print_font import PROFILE,OBSERVED_PROFILE
    if result.get('observed_font_revision',0)<1:
        if result.get('input_font_profile')==PROFILE or ('input_font_profile' not in result and 'input_font_path' not in result):
            result['input_font_profile']=OBSERVED_PROFILE
        result['observed_font_revision']=1
    return result
