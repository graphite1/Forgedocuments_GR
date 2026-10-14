"""Exact-input batch summaries for preview, output and future check sheets."""
from collections import Counter
from decimal import Decimal


def summary(records,number_field,quantity_field,unit_field):
    """Preserve numbers as strings and keep different units separate.

    This does not invent missing numbers, quantities, units or dates. A check
    sheet formatter may consume this same output dataset once specified.
    """
    numbers=[];totals={};missing=0
    for row in records:
        data=row.get('data',row);numbers.append(data.get(number_field,''))
        value=data.get(quantity_field,'')
        if value=='':missing+=1;continue
        quantity=Decimal(value)
        if not quantity.is_finite():raise ValueError('集計対象の数量は有限の数値で指定してください')
        unit=data.get(unit_field,'')
        totals[unit]=totals.get(unit,Decimal(0))+quantity
    return {'count':len(numbers),'numbers':numbers,'duplicates':[n for n,count in Counter(numbers).items() if n and count>1],
            'quantity_totals':{unit:format(value,'f') for unit,value in totals.items()},'missing_quantity_count':missing}
