def calculate_levels(entry,sl,direction,tp1_r=1.0,tp2_r=2.0):
    risk=abs(float(entry)-float(sl))
    if risk<=0: raise ValueError('stop loss must differ from entry')
    if direction=='CALL': tp1=entry+risk*tp1_r; tp2=entry+risk*tp2_r
    elif direction=='PUT': tp1=entry-risk*tp1_r; tp2=entry-risk*tp2_r
    else: raise ValueError('direction must be CALL or PUT')
    if direction=='CALL' and not sl<entry<tp1<tp2: raise ValueError('invalid CALL level ordering')
    if direction=='PUT' and not sl>entry>tp1>tp2: raise ValueError('invalid PUT level ordering')
    return {'entry':float(entry),'sl':float(sl),'tp1':float(tp1),'tp2':float(tp2),'risk':risk,'rr':float(tp2_r)}
