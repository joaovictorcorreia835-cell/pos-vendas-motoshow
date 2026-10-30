"""Planilha mensal informada pelo usuário, independente dos atendimentos individuais."""
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort
from sqlalchemy.exc import IntegrityError
from carregamento import atendimentos
from models import db, Configuracao, FaturamentoMensal, FaturamentoConsultor, Passagem

bp = Blueprint('mensal', __name__)

@bp.post('/faturamento/metas')
def salvar_metas():
    if not getattr(g.usuario,'administrador',False):abort(403)
    from central_models import MetaFaturamento, ConfiguracaoCentral
    from central_service import PESOS
    try:
        ano=int(request.form['ano']);mes=int(request.form['mes'])
        if not 2000<=ano<=2100 or not 1<=mes<=12:raise ValueError()
        unidade=request.form['unidade'].strip()
        if not unidade or len(unidade)>100:raise ValueError()
        valores={k:money(request.form[k]) for k in ('os_centavos','balcao_centavos','mao_centavos')}
        total=money(request.form['total'])
        taxa=Decimal(request.form['crescimento'].replace(',','.'))
        if any(v<=0 for v in valores.values()) or total!=sum(valores.values()) or not taxa.is_finite() or not 0<taxa<=100 or taxa.as_tuple().exponent < -2:raise ValueError()
    except (KeyError,ValueError,InvalidOperation):abort(400,description='Revise as metas positivas, a soma das categorias e o percentual de crescimento.')
    competencia=f'{ano:04d}-{mes:02d}'
    row=db.session.scalar(db.select(MetaFaturamento).where(MetaFaturamento.unidade==unidade,MetaFaturamento.competencia==competencia))
    if not row:row=MetaFaturamento(unidade=unidade,competencia=competencia);db.session.add(row)
    for k,v in valores.items():setattr(row,k,v)
    row.crescimento_percentual=taxa;row.atualizado_por=g.usuario.id;row.atualizado_em=datetime.now()
    central=db.session.scalar(db.select(ConfiguracaoCentral).where(ConfiguracaoCentral.unidade==unidade,ConfiguracaoCentral.competencia==competencia))
    if not central:
        central=ConfiguracaoCentral(unidade=unidade,competencia=competencia,pesos=dict(PESOS));db.session.add(central)
    central.meta_centavos=total;central.atualizado_por=g.usuario.id;central.atualizado_em=datetime.now()
    db.session.commit()
    from flask import current_app
    cache=current_app.extensions.get('central_cache')
    if cache:
        with cache['lock']:cache['rows'].clear()
    flash('Metas por categoria e objetivo de crescimento salvos.','success')
    return redirect(url_for('mensal.painel',ano=ano,mes=mes,unidade=unidade))
MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
CAMPOS = ['os_centavos','balcao_centavos','mao_centavos','pendentes_centavos']

def funcao_linha(row):
    from indicadores import normal
    get = row.get if isinstance(row, dict) else lambda k, default=None: getattr(row,k,default)
    explicit=get('funcao')
    if explicit in ['consultor','mecanico']: return explicit
    name=normal(get('nome',''))
    if get('codigo') in ['22509','22737','33478','64684','71294'] or name in ['jefferson','jefferon','heriky','leandro','hugo','pedro henrique']:
        return 'mecanico'
    if get('mao_centavos',0) and not get('os_centavos',0) and not get('balcao_centavos',0): return 'mecanico'
    return 'consultor'

def money(text, allow_negative=False):
    text = str(text or '').strip().replace('R$', '').replace(' ', '')
    if not text or text == '-': return 0
    if ',' in text: text = text.replace('.', '').replace(',', '.')
    try: number = Decimal(text)
    except InvalidOperation: raise ValueError('Informe valores monetários válidos, como 1.250,00.')
    if not number.is_finite() or (number < 0 and not allow_negative) or abs(number) > Decimal('999999999.99'):
        raise ValueError('Os valores devem estar entre zero e R$ 999.999.999,99.')
    if number != number.quantize(Decimal('.01')): raise ValueError('Use no máximo duas casas decimais.')
    return int(number * 100)

def shift(ano, mes, offset):
    n = ano * 12 + mes - 1 + offset
    return n // 12, n % 12 + 1

def totals(record):
    if record is None: return None
    amounts = {key: sum(getattr(row, key) for row in record.linhas) for key in CAMPOS}
    amounts['total'] = sum(amounts[key] for key in CAMPOS[:3])
    return amounts

def change(current, previous):
    if current is None or previous is None: return dict(delta=None, percent=None, label='Sem mês anterior informado', direction='neutral')
    delta = current - previous
    if previous == 0:
        return dict(delta=delta, percent=0 if current == 0 else None, label='Sem movimento' if current == 0 else 'Sem base percentual (anterior zerado)', direction='up' if delta > 0 else 'neutral')
    pct = delta * 100 / previous
    return dict(delta=delta, percent=pct, label=('Crescimento' if delta > 0 else 'Queda' if delta < 0 else 'Estável'), direction='up' if delta > 0 else 'down' if delta < 0 else 'neutral')

def faturamento_consultores(ano,mes,unidade,record=None,fonte='movimentos'):
    groups={}
    def add(nome,os_value,balcao):
        if not os_value and not balcao: return
        key=nome.strip().casefold()
        if key not in groups: groups[key]=dict(nome=nome,os_centavos=0,balcao_centavos=0,total=0)
        row=groups[key]
        for field,value in [('os_centavos',os_value),('balcao_centavos',balcao)]: row[field]+=value
        row['total']+=os_value+balcao
    if fonte=='planilha':
        for row in record.linhas if record else []:
            if funcao_linha(row)=='consultor': add(row.nome,row.os_centavos,row.balcao_centavos)
    else:
        start=datetime(ano,mes,1);y,m=shift(ano,mes,1);end=datetime(y,m,1)
        rows=db.session.scalars(db.select(Passagem).options(*atendimentos()).where(Passagem.unidade==unidade,Passagem.data>=start,Passagem.data<end,Passagem.status=='Finalizada')).all()
        for p in rows:
            nome=p.consultor.nome if p.consultor else 'Não informado'
            if p.tipo=='Balcão':
                if p.venda_balcao and p.venda_balcao.natureza=='Devolução': continue
                add(nome,0,p.total-sum(i.valor_liquido for i in p.itens if i.categoria=='M\u00e3o de obra'))
            elif p.ordem:
                mao=sum(i.valor_liquido for i in p.itens if i.categoria=='Mão de obra')
                add(nome,p.total-mao,0)
    rows=sorted(groups.values(),key=lambda r:(-r['total'],r['nome']))
    totals={key:sum(r[key] for r in rows) for key in ['os_centavos','balcao_centavos','total']}
    for row in rows: row['percentual']=100*row['total']/totals['total'] if totals['total'] else 0
    return dict(linhas=rows,totais=totals)

@bp.route('/faturamento', methods=['GET', 'POST'])
def painel():
    source = request.form if request.method == 'POST' else request.args
    try:
        ano = int(source.get('ano', date.today().year)); mes = int(source.get('mes', date.today().month))
        if not 2000 <= ano <= 2100 or not 1 <= mes <= 12: raise ValueError()
    except ValueError:
        flash('Selecione um mês e ano válidos (2000 a 2100).', 'danger')
        return redirect(url_for('mensal.painel'))
    unidade = source.get('unidade', '').strip() or db.session.get(Configuracao, 1).unidade
    if len(unidade) > 100:
        flash('Nome da unidade muito longo.', 'danger'); return redirect(url_for('mensal.painel'))
    record = db.session.scalar(db.select(FaturamentoMensal).where(FaturamentoMensal.ano==ano, FaturamentoMensal.mes==mes, FaturamentoMensal.unidade==unidade))
    submitted = None
    if request.method == 'POST':
        try:
            submitted = json.loads(request.form.get('linhas', '[]'))
            if not isinstance(submitted, list) or len(submitted) > 200: raise ValueError('Use até 200 linhas por mês.')
            clean = []; codes = set()
            for index, row in enumerate(submitted, 1):
                if not isinstance(row, dict): raise ValueError('Linha inválida.')
                codigo = str(row.get('codigo', '')).strip().upper(); nome = str(row.get('nome', '')).strip()
                amounts = {key: money(row.get(key, ''), allow_negative=key=='balcao_centavos') for key in CAMPOS}
                if not codigo and not nome and not any(amounts.values()): continue
                if not codigo or not nome: raise ValueError(f'Linha {index}: informe código e consultor.')
                if len(codigo) > 30 or len(nome) > 160: raise ValueError(f'Linha {index}: código ou nome muito longo.')
                if codigo in codes: raise ValueError(f'Código {codigo} repetido neste mês.')
                funcao=row.get('funcao') or funcao_linha(dict(codigo=codigo,nome=nome,**amounts))
                if funcao not in ['consultor','mecanico']: raise ValueError('Função inválida.')
                codes.add(codigo); clean.append(dict(codigo=codigo, nome=nome, funcao=funcao, **amounts))
            version = int(request.form.get('versao', '0'))
            if record:
                updated = db.session.execute(db.update(FaturamentoMensal).where(FaturamentoMensal.id==record.id, FaturamentoMensal.versao==version).values(versao=version+1, atualizado_em=datetime.now()))
                if updated.rowcount != 1: raise ValueError('Este mês foi alterado em outra aba. Recarregue a página antes de salvar.')
                record.linhas.clear()
                db.session.flush()
            else:
                if version: raise ValueError('Este mês foi alterado. Recarregue a página.')
                record = FaturamentoMensal(ano=ano, mes=mes, unidade=unidade)
                db.session.add(record)
            record.linhas.extend(FaturamentoConsultor(**row) for row in clean)
            db.session.commit()
            flash('Faturamento mensal salvo. Gráfico e comparações atualizados.', 'success')
            return redirect(url_for('mensal.painel', ano=ano, mes=mes, unidade=unidade))
        except (ValueError, TypeError, InvalidOperation) as exc:
            db.session.rollback(); flash(str(exc), 'danger')
            if not isinstance(submitted, list) or any(not isinstance(r, dict) for r in submitted): submitted = None
        except IntegrityError:
            db.session.rollback(); flash('Este mês foi atualizado em outra aba. Recarregue antes de salvar.', 'danger')
    # Meses sem lançamento permanecem distintos de meses salvos com valor zero.
    records = db.session.scalars(db.select(FaturamentoMensal).where(FaturamentoMensal.unidade==unidade)).all()
    by_month = {(r.ano, r.mes): r for r in records}
    selected = totals(record)
    previous_key = shift(ano, mes, -1); previous = totals(by_month.get(previous_key))
    comparison = change(selected['total'] if selected else None, previous['total'] if previous else None)
    history = []
    for offset in range(-11, 1):
        y, m = shift(ano, mes, offset); value = totals(by_month.get((y, m))); prev = totals(by_month.get(shift(y, m, -1)))
        history.append(dict(ano=y, mes=m, label=f'{MESES[m-1][:3]}/{y}', values=value, change=change(value['total'] if value else None, prev['total'] if prev else None)))
    if submitted is not None:
        initial = [{key: str(row.get(key, '')) for key in ['codigo','nome','funcao']+CAMPOS} for row in submitted]
    else:
        initial = [dict(codigo=r.codigo, nome=r.nome, funcao=funcao_linha(r), **{k: f'{getattr(r,k)/100:.2f}' for k in CAMPOS}) for r in record.linhas] if record else []
    previous_consultants = {r.codigo:r for r in by_month[previous_key].linhas} if previous_key in by_month else {}
    consultants = []
    current_consultants = {r.codigo:r for r in record.linhas} if record else {}
    for code in sorted(set(previous_consultants) | set(current_consultants)):
        current = current_consultants.get(code); old = previous_consultants.get(code)
        consultants.append(dict(codigo=code, nome=(current or old).nome, funcao=funcao_linha(current or old), current=current.total if current else 0, previous=old.total if old else 0, change=change(current.total if current else 0, old.total if old else 0) if record and previous is not None else change(None,None)))
    units = sorted(set([unidade, db.session.get(Configuracao,1).unidade]+[r.unidade for r in db.session.scalars(db.select(FaturamentoMensal)).all()]))
    fonte_consultores=request.args.get('fonte_consultores','movimentos')
    if fonte_consultores not in ['movimentos','planilha']: fonte_consultores='movimentos'
    ranking=faturamento_consultores(ano,mes,unidade,record,fonte_consultores)
    from central_models import ConfiguracaoCentral
    meta_config = db.session.scalar(db.select(ConfiguracaoCentral).where(ConfiguracaoCentral.unidade==unidade, ConfiguracaoCentral.competencia==f'{ano:04d}-{mes:02d}'))
    meta_centavos = meta_config.meta_centavos if meta_config else None
    from services.monthly_goals import plano
    import calendar
    plano_metas=plano(ano,mes,unidade)
    metas_categorias={r['chave']:r['meta'] for r in plano_metas['categorias']} if plano_metas else {}
    return render_template('faturamento.html',plano_metas=plano_metas,metas_categorias=metas_categorias,month_end=calendar.monthrange(ano,mes)[1],meta_centavos=meta_centavos,ranking=ranking,fonte_consultores=fonte_consultores, page='faturamento', ano=ano, mes=mes, meses=MESES, unidade=unidade, units=units, record=record, initial=initial, selected=selected, previous=previous, comparison=comparison, history=history, consultants=consultants, previous_label=f'{MESES[previous_key[1]-1]} / {previous_key[0]}', next_key=shift(ano,mes,1), previous_key=previous_key, today=date.today())
