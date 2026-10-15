"""Transport planning data only. Generated records are marked as simulation."""
from datetime import datetime
from pathlib import Path
import csv,json,math,random
from .receipt import render_receipt

def minute(value):
    try:
        h,m=map(int,str(value).split(':'))
        if not 0<=h<24 or not 0<=m<60: raise ValueError()
        return h*60+m
    except (ValueError,TypeError): raise ValueError('時刻はHH:MMで指定してください')

def hhmm(value): return f'{value//60:02d}:{value%60:02d}'

def periods(config):
    start,end=minute(config['start']),minute(config['end'])
    if start>=end: raise ValueError('終了時刻は開始時刻より後にしてください。日付をまたぐ運行には未対応です')
    rests=[]
    for a,b in config.get('breaks',[]):
        a,b=minute(a),minute(b)
        if a>=b: raise ValueError('休憩の終了時刻は開始時刻より後にしてください')
        if b>start and a<end: rests.append((max(start,a),min(end,b)))
    rests.sort();merged=[]
    for a,b in rests:
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else: merged.append((a,b))
    slots=[];at=start
    for a,b in merged:
        if at<a: slots.append((at,a))
        at=b
    if at<end: slots.append((at,end))
    if not slots: raise ValueError('稼働時間がありません。休憩時間を確認してください')
    return slots

def real_minute(active,slots):
    for a,b in slots:
        if active<b-a: return a+active
        active-=b-a
    return slots[-1][1]-1

def distribute(units,ratios):
    raw=[units*r/sum(ratios) for r in ratios]
    parts=[int(x) for x in raw]
    order=sorted(range(len(parts)),key=lambda i:raw[i]-parts[i],reverse=True)
    for i in order[:units-sum(parts)]: parts[i]+=1
    return parts

def plan_runs(config,vehicle):
    return 2 if config.get('measurement_mode','count')=='fixed' else int(vehicle['runs'])

def active_minute_of(value,slots):
    t=minute(value);elapsed=0
    for a,b in slots:
        if a<=t<b:return elapsed+t-a
        elapsed+=b-a
    raise ValueError('指定した計量時刻が休憩または稼働時間外にあります')

def make_plan(config,vehicles):
    date=datetime.strptime(config['date'],'%Y-%m-%d').strftime('%d/%m/%Y')
    slots=periods(config);active=sum(b-a for a,b in slots)
    gap=int(config.get('minimum_trip_minutes',30));jitter=int(config.get('time_jitter_minutes',10))
    bridge_gap=int(config.get('scale_gap_minutes',2))
    if gap<1 or jitter<0 or bridge_gap<0: raise ValueError('最短運搬間隔は1分以上、ばらつき・計量間隔は0以上で指定してください')
    if not vehicles: raise ValueError('車両が未設定です')
    if len(vehicles)>50:raise ValueError('車両は50台以内で指定してください')
    fixed=config.get('measurement_mode','count')=='fixed'
    if config.get('measurement_mode','count') not in ('count','fixed'):raise ValueError('予定の作成方法が不明です')
    if len({v['vehicle'] for v in vehicles})!=len(vehicles): raise ValueError('車両名が重複しています')
    seed=config.get('seed')
    rng=random.Random(None if seed in (None,'') else seed)
    first_sn=int(config.get('first_sn',1))
    if not 0<=first_sn<=9999: raise ValueError('SN開始値は0～9999です')
    # runs counts loaded hauls; every vehicle has one additional initial tare measurement.
    total_runs=sum(plan_runs(config,v)+1 for v in vehicles)
    if not fixed and first_sn+total_runs-1>9999: raise ValueError('生成されるSNが4桁を超えます')
    records=[];occupied=[]
    for vi,v in enumerate(vehicles):
        name=str(v['vehicle']).strip();runs=plan_runs(config,v)
        tare=int(v['tare_kg']);max_payload=int(v['max_payload_kg']);max_gross=int(v['max_gross_kg'])
        target=int(v['target_payload_kg']);variation=int(v['weight_jitter_kg'])
        if not name or not 1<=runs<=100: raise ValueError('各車の名前と運搬回数（1～100）を指定してください')
        if tare<=0 or tare%10: raise ValueError('試算の空車重量は正の10kg単位で指定してください')
        if min(max_payload,max_gross,target,variation)<0: raise ValueError('重量上限・基準重量・振幅は0以上で指定してください')
        cap=min(max_payload,max_gross-tare)
        if cap<0 or target>cap: raise ValueError(name+'：基準積載重量が上限を超えています')
        low=math.ceil(max(0,target-variation)/10);high=math.floor(min(cap,target+variation)/10)
        if low>high: raise ValueError(name+'：10kg刻みで生成できる重量がありません')
        measurements=runs+1
        slack=active-1-runs*gap
        if slack<0: raise ValueError(name+'：初回空車計量を含む指定回数と最短運搬間隔を稼働時間内に収められません')
        extra_step=slack/measurements
        # Fixed measurements retain the exact user-specified time and SN.
        if fixed:
            specified=v.get('fixed_measurements',[])
            if len(specified)!=3:raise ValueError(name+'：空車・積載・積載の3回の時刻とSNを指定してください')
            times=[active_minute_of(s['time'],slots) for s in specified]
        # Stratify throughout active hours; randomness stays feasible rather than clipping time to a boundary.
        for attempt in range(0 if fixed else 500):
            times=[];previous=-1;candidate_ok=True
            for run in range(measurements):
                center=run*gap+(run+0.45)*extra_step
                amplitude=min(jitter,extra_step/2)
                proposed=int(round(center+rng.uniform(-amplitude,amplitude)))
                proposed=max(0,min(active-1,proposed))
                choices=list(range(max(0,math.ceil(center-amplitude)),min(active-1,math.floor(center+amplitude))+1))
                if proposed in choices: choices.remove(proposed)
                choices.insert(0,proposed)
                chosen=None
                for t in choices:
                    real=real_minute(t,slots)
                    if previous>=0 and t-previous<gap: continue
                    if any(abs(real-o)<bridge_gap for o in occupied): continue
                    if any(abs(real-real_minute(q,slots))<bridge_gap for q in times): continue
                    chosen=t;break
                if chosen is None: candidate_ok=False;break
                times.append(chosen);previous=chosen
            if candidate_ok: break
        else:
            if not fixed:raise ValueError(name+'：休憩・回数・最短間隔・台数を同時に満たす計量時刻を作れません。条件を調整してください')
        tare_axles=distribute(tare//10,[2520,2290,2020,1960,1870,2010])
        for run,t in enumerate(times,1):
            payload=0 if run==1 else rng.randint(low,high)*10
            shares=[r*rng.uniform(0.9,1.1) for r in [0.05,0.05,0.225,0.225,0.225,0.225]]
            load=distribute(payload//10,shares)
            axles=[10*(a+b) for a,b in zip(tare_axles,load)]
            record={'excel_row':0,'date':date,'time':hhmm(real_minute(t,slots)),
                    'sn':str(specified[run-1]['sn']).zfill(4) if fixed else '0000',
                    'vehicle':name,'trip':str(run),'haul_trip':run-1,
                    'category':'空車' if run==1 else '積載',
                    'mode':'simulation','axle_values_kg':axles,
                    'axle_totals_kg':[sum(axles[i:i+2]) for i in (0,2,4)],
                    'total_kg':sum(axles),'tare_kg':tare,'payload_kg':payload,
                    'record_id':f'PLAN_{config["date"]}_{vi+1}_{run}',
                    'max_payload_kg':max_payload,'max_gross_kg':max_gross,
                    'active_minute':t}
            assert record['total_kg']<=max_gross and payload<=max_payload
            records.append(record);occupied.append(real_minute(t,slots))
    records.sort(key=lambda r:(r['time'],r['vehicle']))
    for index,r in enumerate(records):
        if not fixed:r['sn']=str(first_sn+index).zfill(4)
        r['excel_row']=index+1
    validate_plan(records,config,vehicles)
    return records

def validate_plan(records,config,vehicles):
    slots=periods(config);by_name={v['vehicle']:v for v in vehicles}
    if len(by_name)!=len(vehicles):raise ValueError('車両名が重複しています')
    sn=set();previous={};counts={};trips={}
    date=datetime.strptime(config['date'],'%Y-%m-%d').strftime('%d/%m/%Y')
    gap=int(config.get('minimum_trip_minutes',30));bridge_gap=int(config.get('scale_gap_minutes',2))
    if gap<1 or bridge_gap<0:raise ValueError('最短運搬間隔は1分以上、計量間隔は0以上です')
    if not vehicles or len(vehicles)>50:raise ValueError('車両は1～50台です')
    ordered=sorted(records,key=lambda r:r['time']);previous_scale=None
    for r in ordered:
        if r.get('mode')!='simulation' or r['vehicle'] not in by_name or r['date']!=date:raise ValueError('試算の区分・車両・日付が設定と一致しません')
        v=by_name[r['vehicle']];t=minute(r['time'])
        if not any(a<=t<b for a,b in slots):raise ValueError('計量予定が休憩または稼働時間外にあります')
        active=0
        for a,b in slots:
            if a<=t<b:active+=t-a;break
            active+=b-a
        if r['vehicle'] in previous and active-previous[r['vehicle']]<gap:raise ValueError('同じ車両の最短運搬間隔を満たしていません')
        previous[r['vehicle']]=active
        if previous_scale is not None and t-previous_scale<bridge_gap:raise ValueError('計量器の最短間隔を満たしていません')
        previous_scale=t
        if len(r['sn'])!=4 or not r['sn'].isascii() or not r['sn'].isdigit() or r['sn'] in sn:raise ValueError('SNが4桁の一意な番号ではありません')
        sn.add(r['sn']);counts[r['vehicle']]=counts.get(r['vehicle'],0)+1
        trip=int(r['trip']);trips.setdefault(r['vehicle'],set())
        if trip in trips[r['vehicle']]:raise ValueError('回数番号が重複しています')
        trips[r['vehicle']].add(trip)
        if trip!=counts[r['vehicle']]:raise ValueError('計量回数が時刻順になっていません')
        if r.get('haul_trip')!=trip-1:raise ValueError('計量回数と運搬回数が一致しません')
        if r.get('category')!=('空車' if trip==1 else '積載'):raise ValueError('各車の第1回は空車計量、第2回以降は積載計量にしてください')
        if config.get('measurement_mode')=='fixed':
            specified=v.get('fixed_measurements',[])
            if len(specified)!=3 or not 1<=trip<=3:raise ValueError('指定計量は空車・積載・積載の3回です')
            s=specified[trip-1]
            if r['time']!=hhmm(minute(s['time'])) or r['sn']!=str(s['sn']).zfill(4):raise ValueError('出力時刻・SNが指定内容と一致しません')
        axles=r['axle_values_kg'];payload=r['payload_kg'];total=r['total_kg']
        if len(axles)!=6 or any(x<0 or x%10 for x in axles) or payload%10:raise ValueError('試算重量が10kg単位ではありません')
        if total!=sum(axles) or total-r['tare_kg']!=payload or r['tare_kg']!=v['tare_kg']:raise ValueError('総重量・空車・積載・軸重量が整合していません')
        if trip==1 and (payload!=0 or total!=v['tare_kg']):raise ValueError('初回空車計量の総重量は設定した空車重量にしてください')
        if r['axle_totals_kg']!=[sum(axles[i:i+2]) for i in (0,2,4)]:raise ValueError('軸計が一致しません')
        if total>v['max_gross_kg'] or payload>v['max_payload_kg'] or payload<0:raise ValueError('重量が設定上限を超えています')
    for v in vehicles:
        runs=plan_runs(config,v)
        if counts.get(v['vehicle'],0)!=runs+1 or trips.get(v['vehicle'],set())!=set(range(1,runs+2)):raise ValueError('空車1回＋設定した運搬回数と生成された計量回数が一致しません')
    return True

def export_plan(records,config,vehicles,folder,paper='a4'):
    validate_plan(records,config,vehicles)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    images=[]
    for record in records:
        if record.get('mode')!='simulation': raise ValueError('試算データ以外を計画出力へ混在させないでください')
        image,name=render_receipt(record,folder,paper=paper);images.append(folder/(name+'.png'))
    if images:
        from .pdf_bundle import combine_png_pages
        combine_png_pages(images,folder/'全レシート.pdf')
    document={'mode':'simulation','config':config,'vehicles':vehicles,'records':records}
    (folder/'運搬記録.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
    with (folder/'運搬記録.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['データ区分','日付','車両','計量回数','区分','運搬回数','時刻','SN','空車kg','積載kg','総重量kg','総重量上限kg'])
        writer.writerows([['試算',r['date'],r['vehicle'],r['trip'],r['category'],r['haul_trip'],r['time'],r['sn'],r['tare_kg'],r['payload_kg'],r['total_kg'],r['max_gross_kg']] for r in records])
    counts={v['vehicle']:sum(r['vehicle']==v['vehicle'] and r['category']=='積載' for r in records) for v in vehicles}
    (folder/'実行結果.txt').write_text('運搬計画・試算\n'+f'台数 {len(vehicles)} / 計量予定 {len(records)}件\n'+
      '\n'.join(f'{k}: 空車1回＋運搬{v}回（計量{v+1}回）' for k,v in counts.items())+'\n'+f'想定積載重量合計 {sum(r["payload_kg"] for r in records):,}kg\n'+
      '休憩時間中の計量なし。各車の総重量・積載重量の設定上限以内。\n軸左右の内訳は試算配分です。実測の軸荷重ではありません。\n',encoding='utf-8-sig')
    return folder
