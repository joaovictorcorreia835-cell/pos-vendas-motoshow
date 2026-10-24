"""Interface do inventário integrada ao login e ao CSRF existentes."""
import io
import secrets
import zlib
from datetime import date
from collections import Counter
from functools import wraps
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import StaleDataError
from inventario_models import *
import inventario_service as svc
from models import Usuario

bp=Blueprint('inventario',__name__,url_prefix='/patio')


def mutacao(minimo):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            svc.permitir(minimo)
            try:
                if db.engine.dialect.name=='sqlite':
                    raw=db.session.connection().connection.driver_connection
                    if not raw.in_transaction:
                        db.session.execute(text('BEGIN IMMEDIATE'))
                response=fn(*args,**kwargs)
                db.session.commit()
                return response
            except (ValueError,KeyError,TypeError,IntegrityError,StaleDataError,OperationalError) as error:
                db.session.rollback()
                message=str(error) if isinstance(error,ValueError) else 'Conflito ou dados inválidos. Atualize a página e tente novamente.'
                if request.accept_mimetypes.best=='application/json':
                    return jsonify(error=message),409
                flash(message,'danger')
                return redirect(request.path if request.method=='GET' else url_for('inventario.inventarios') if '/inventarios' in request.path else url_for('inventario.mestre'))
            except Exception:
                db.session.rollback()
                raise
        return wrapped
    return decorate


@bp.context_processor
def contexto():
    return dict(papel_estoque=svc.papel(),comerciais=svc.COMERCIAIS,
        locais_estoque=db.session.scalars(select(LocalEstoque).where(LocalEstoque.ativo.is_(True)).order_by(LocalEstoque.id)).all(),
        unidades_estoque=db.session.scalars(select(UnidadeEstoque).where(UnidadeEstoque.ativo.is_(True)).order_by(UnidadeEstoque.nome)).all())


def consulta(args=None):
    args=request.args if args is None else args
    query=select(MotoEstoque).options(selectinload(MotoEstoque.localizacao))
    if args.get('situacao')=='saidas':
        query=query.where(MotoEstoque.saida_fisica_confirmada.is_(True))
    elif args.get('situacao')!='todas':
        query=query.where(MotoEstoque.ativo.is_(True),MotoEstoque.saida_fisica_confirmada.is_(False))
    if args.get('unidade'):
        query=query.where(MotoEstoque.unidade_nome==args['unidade'])
    if args.get('localizacao'):
        query=query.join(LocalEstoque).where(db.or_(LocalEstoque.codigo==args['localizacao'],LocalEstoque.grupo==args['localizacao']))
    if args.get('status'):
        query=query.where(MotoEstoque.status_comercial==args['status'])
    if args.get('modelo'):
        query=query.where(MotoEstoque.modelo.contains(args['modelo'],autoescape=True))
    q=args.get('q','').strip()
    if q:
        vin=''.join(c for c in q.upper() if c.isalnum())
        query=query.where(db.or_(MotoEstoque.chassi_normalizado.contains(vin or q,autoescape=True),MotoEstoque.modelo.ilike('%'+q.replace('%','\\%').replace('_','\\_')+'%',escape='\\')))
    if args.get('confirmada') in ('sim','nao'):
        query=query.where(MotoEstoque.presenca_confirmada.is_(args['confirmada']=='sim'))
    pending=select(DivergenciaMoto.moto_id).where(DivergenciaMoto.resolvido.is_(False),DivergenciaMoto.moto_id.is_not(None))
    if args.get('divergencia')=='sim':query=query.where(MotoEstoque.id.in_(pending))
    if args.get('divergencia')=='nao':query=query.where(MotoEstoque.id.not_in(pending))
    rows=db.session.scalars(query.order_by(MotoEstoque.modelo,MotoEstoque.chassi_normalizado)).all()
    if args.get('dias'):
        try: days=int(args['dias'])
        except ValueError: days=45
        rows=[m for m in rows if m.dias_estoque is not None and m.dias_estoque>days]
    if args.get('conferencia'):
        policy=db.session.get(PoliticaEstoque,1)
        rows=[m for m in rows if svc.conferencia_status(m,policy)==args['conferencia']]
    return rows


def render(view,**kwargs):
    return render_template(view,page='patio',**kwargs)


@bp.get('/mestre')
def mestre():
    rows=consulta(); page=max(1,request.args.get('pagina',1,type=int)); per_page=30
    pending={d.moto_id for d in db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.resolvido.is_(False)))}
    policy=db.session.get(PoliticaEstoque,1)
    return render('estoque_mestre.html',rows=rows[(page-1)*per_page:page*per_page],total=len(rows),pagina=page,paginas=max(1,(len(rows)+per_page-1)//per_page),
        indicadores=svc.indicadores(rows),pendentes=pending,policy=policy,conferencia_status=svc.conferencia_status,
        pagina_url=lambda p:url_for('inventario.mestre',**dict(request.args,pagina=p)))


@bp.route('/motos/nova',methods=['GET','POST'])
def nova_moto():
    if request.method=='POST':
        return salvar_nova()
    svc.permitir('GESTOR')
    return render('estoque_cadastro.html',m=None)


@mutacao('GESTOR')
def salvar_nova():
    m=svc.cadastrar(request.form)
    flash('Moto cadastrada sem presumir presença física.','success')
    return redirect(url_for('inventario.ficha',ident=m.id))


@bp.get('/motos/<int:ident>')
def ficha(ident):
    m=db.get_or_404(MotoEstoque,ident)
    events=db.session.scalars(select(MovimentacaoMoto).where(db.or_(MovimentacaoMoto.moto_id==ident,db.and_(MovimentacaoMoto.moto_id.is_(None),MovimentacaoMoto.chassi==m.chassi_normalizado))).order_by(MovimentacaoMoto.data_hora.desc(),MovimentacaoMoto.id.desc())).all()
    differences=db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.moto_id==ident).order_by(DivergenciaMoto.id.desc())).all()
    transfer=svc.pendente_transferencia(m)
    target=db.session.get(UnidadeEstoque,transfer.unidade_destino_id).nome if transfer else ''
    return render('estoque_ficha.html',m=m,eventos=events,divergencias=differences,transferencia=transfer,transferencia_destino=target)


@bp.post('/motos/<int:ident>/acao')
@mutacao('OPERADOR')
def acao_moto(ident):
    m=svc.obter_moto(ident,request.form.get('revisao'))
    action=request.form.get('acao'); note=request.form.get('observacao','').strip()
    if action in ('mover','conferir'):
        svc.mover(m,request.form.get('localizacao'),note,'CONFERÊNCIA RÁPIDA' if action=='conferir' else 'ALTERAÇÃO DE LOCALIZAÇÃO')
    elif action=='receber':
        svc.receber(m,request.form.get('localizacao'),note)
    else:
        svc.permitir('GESTOR')
        if action=='saida':svc.saida(m,request.form.get('destino'),request.form.get('motivo'),request.form.get('responsavel'),note)
        elif action=='retorno':svc.retorno(m,request.form.get('localizacao'),note)
        elif action=='transferir':svc.transferir(m,request.form.get('destino_unidade'),note)
        elif action=='editar':
            if not note:raise ValueError('Correção cadastral exige justificativa.')
            before=svc.estado(m); vin=svc.normalizar_chassi(request.form.get('chassi',m.chassi))
            if db.session.scalar(select(MotoEstoque.id).where(MotoEstoque.chassi_normalizado==vin,MotoEstoque.id!=m.id)):
                raise ValueError('Chassi já cadastrado.')
            m.chassi=m.chassi_normalizado=vin
            for key,size in [('modelo',200),('cor',100),('versao',100),('ano_modelo',4),('ano_fabricacao',4),('numero_motor',100),('numero_nf',80)]:
                value=request.form.get(key,getattr(m,key)) or ''
                if len(value)>size:raise ValueError('Campo muito longo: '+key)
                setattr(m,key,value)
            if not m.modelo:raise ValueError('Modelo obrigatório.')
            if request.form.get('status_comercial') not in svc.COMERCIAIS:raise ValueError('Status inválido.')
            m.status_comercial=request.form['status_comercial']
            if request.form.get('data_entrada'):
                entered=date.fromisoformat(request.form['data_entrada'])
                if entered>agora().date():raise ValueError('Entrada no futuro não é permitida.')
                m.data_entrada=entered
            svc.auditar(m,'CORREÇÃO CADASTRAL',before,note)
        else:raise ValueError('Ação inválida.')
    flash('Operação registrada no histórico.','success')
    return redirect(url_for('inventario.ficha',ident=m.id))


@bp.get('/localizar')
def localizar():
    rows=consulta(dict(request.args,situacao='todas'))[:20] if request.args.get('q') else []
    return render('estoque_rapida.html',rows=rows)


@bp.get('/api/localizar')
def api_localizar():
    rows=consulta(dict(request.args,situacao='todas'))[:20] if request.args.get('q') else []
    pending={d.moto_id for d in db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.resolvido.is_(False)))}
    return jsonify(motos=[dict(id=m.id,chassi=m.chassi_normalizado,modelo=m.modelo,cor=m.cor,unidade=m.unidade_nome,localizacao=m.localizacao.nome,status=m.status_comercial,
        ultima_conferencia=m.data_ultima_confirmacao.isoformat() if m.data_ultima_confirmacao else None,dias_estoque=m.dias_estoque,divergencia=m.id in pending) for m in rows])


@bp.get('/inventarios')
def inventarios():
    rows=db.session.scalars(select(InventarioMoto).order_by(InventarioMoto.id.desc())).all()
    return render('estoque_inventarios.html',rows=rows)


@bp.post('/inventarios/novo')
@mutacao('GESTOR')
def novo_inventario():
    inv=svc.abrir_inventario(request.form.get('unidade_id'),request.form.get('nome',''),request.form.get('primeiro')=='sim',request.form.get('escopo','todos')=='todos')
    return redirect(url_for('inventario.contagem',ident=inv.id))


@bp.get('/inventarios/<int:ident>')
def contagem(ident):
    inv=db.get_or_404(InventarioMoto,ident)
    q=request.args.get('chassi','').strip(); match=None; duplicate=None
    if q:
        try:
            vin=svc.normalizar_chassi(q)
            match=db.session.scalar(select(MotoEstoque).where(MotoEstoque.chassi_normalizado==vin))
            duplicate=db.session.scalar(select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==ident,InventarioMotoItem.chassi==vin,InventarioMotoItem.encontrado.is_(True)))
        except ValueError as error:flash(str(error),'warning')
    items=db.session.scalars(select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==ident).order_by(InventarioMotoItem.conferido_em.desc(),InventarioMotoItem.id)).all()
    return render('estoque_contagem.html',inv=inv,resumo=svc.resumo_inventario(inv),items=items,match=match,q=q,duplicada=duplicate)


@bp.post('/inventarios/<int:ident>/conferir')
@mutacao('OPERADOR')
def conferir(ident):
    inv=svc.inventario_aberto(ident)
    result=svc.conferir(inv,request.form.get('chassi'),request.form.get('localizacao'),request.form.get('corrigir')=='sim',request.form.get('observacao',''))
    if result['duplicada']:
        item=result['item']
        flash(f'MOTO JÁ CONFERIDA: {item.conferido_em:%d/%m/%Y %H:%M} por {item.conferido_por}, em {item.localizacao_encontrada}. A quantidade não foi incrementada.','warning')
    else:flash('Moto conferida. Próximo chassi.','success')
    return redirect(url_for('inventario.contagem',ident=ident)+'#scanner')


@bp.post('/inventarios/<int:ident>/analisar')
@mutacao('GESTOR')
def analisar(ident):
    svc.analisar(svc.inventario_aberto(ident))
    return redirect(url_for('inventario.divergencias',inventario=ident))


@bp.post('/inventarios/<int:ident>/encerrar')
@mutacao('GESTOR')
def encerrar(ident):
    svc.encerrar(svc.inventario_aberto(ident),request.form.get('observacao',''),request.form.get('cancelar')=='sim')
    flash('Resultado final registrado e bloqueado para alterações.','success')
    return redirect(url_for('inventario.contagem',ident=ident))


@bp.get('/divergencias')
def divergencias():
    query=select(DivergenciaMoto)
    if request.args.get('inventario',type=int):query=query.where(DivergenciaMoto.inventario_id==request.args.get('inventario',type=int))
    if request.args.get('situacao')!='todas':query=query.where(DivergenciaMoto.resolvido.is_(False))
    rows=db.session.scalars(query.order_by(DivergenciaMoto.id.desc())).all()
    motos={m.id:m for m in db.session.scalars(select(MotoEstoque).where(MotoEstoque.id.in_({d.moto_id for d in rows if d.moto_id})))}
    inventories={i.id:i for i in db.session.scalars(select(InventarioMoto).where(InventarioMoto.id.in_({d.inventario_id for d in rows if d.inventario_id})))}
    for d in rows:
        m=motos.get(d.moto_id); inv=inventories.get(d.inventario_id)
        d.modelo=m.modelo if m else 'Não cadastrada'
        d.unidade_nome=inv.unidade_nome if inv else m.unidade_nome if m else 'Fonte importada'
        d.bloqueada=bool(inv and inv.status in ('CONCLUÍDO','CANCELADO'))
    return render('estoque_divergencias.html',rows=rows)


@bp.post('/divergencias/<int:ident>/resolver')
@mutacao('GESTOR')
def resolver(ident):
    d=db.session.scalar(select(DivergenciaMoto).where(DivergenciaMoto.id==ident).with_for_update())
    if not d:abort(404)
    svc.resolver(d,request.form.get('justificativa',''),request.form.get('acao','JUSTIFICAR'),request.form.get('localizacao'),dict(request.form))
    flash('Resolução registrada com auditoria.','success')
    return redirect(url_for('inventario.divergencias',inventario=d.inventario_id) if d.inventario_id else url_for('inventario.divergencias'))


@bp.get('/pdv')
def pdv():
    rows=consulta(dict(request.args,localizacao='PDV'))
    return render('estoque_pdv.html',rows=rows,agora=agora())


@bp.get('/relatorio-estoque')
def relatorio():
    rows=consulta(); stats=svc.indicadores(rows); policy=db.session.get(PoliticaEstoque,1)
    groups={label:dict(Counter(getter(m) for m in rows)) for label,getter in [('Unidade',lambda m:m.unidade_nome),('Localização',lambda m:m.localizacao.nome),('Modelo',lambda m:m.modelo),('Status comercial',lambda m:m.status_comercial)]}
    totals=dict(faturadas_presentes=sum(m.presenca_confirmada and not m.saida_fisica_confirmada and m.status_comercial=='FATURADA' for m in rows),
        vendidas_presentes=sum(m.presenca_confirmada and not m.saida_fisica_confirmada and m.status_comercial=='VENDIDA' for m in rows),
        nao_conferidas=sum(svc.conferencia_status(m,policy) in ('NUNCA CONFERIDA','CONFERÊNCIA VENCIDA') for m in rows),
        dias={d:sum(m.dias_estoque is not None and m.dias_estoque>d for m in rows) for d in (15,30,45,60,90)})
    headers=['Chassi','Modelo','Cor','Unidade','Status comercial','Localização','Presença confirmada','Dias em estoque','Última conferência','Responsável','Saída física confirmada']
    data=[[m.chassi_normalizado,m.modelo,m.cor,m.unidade_nome,m.status_comercial,m.localizacao.nome,'Sim' if m.presenca_confirmada and not m.saida_fisica_confirmada else 'Não',m.dias_estoque,m.data_ultima_confirmacao,m.usuario_ultima_confirmacao,'Sim' if m.saida_fisica_confirmada else 'Não'] for m in rows]
    if request.args.get('export')=='xlsx':
        from exportacoes import workbook_response
        return workbook_response('Estoque de motos',headers,data,'estoque_motos.xlsx',set(),{9},set())
    if request.args.get('export')=='pdf':
        from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape,A4
        from reportlab.lib.styles import getSampleStyleSheet
        from xml.sax.saxutils import escape
        stream=io.BytesIO(); style=getSampleStyleSheet(); style['BodyText'].fontSize=6; style['BodyText'].leading=8
        values=[[Paragraph(escape(str(v or '')),style['BodyText']) for v in row] for row in [headers]+data]
        table=Table(values,repeatRows=1,colWidths=[740/len(headers)]*len(headers));table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.lightblue),('VALIGN',(0,0),(-1,-1),'TOP')]))
        SimpleDocTemplate(stream,pagesize=landscape(A4),leftMargin=25,rightMargin=25).build([Paragraph('Motoshow — Estoque de motos',style['Title']),Spacer(1,12),table]);stream.seek(0)
        return send_file(stream,as_attachment=True,download_name='estoque_motos.pdf')
    return render('estoque_relatorio.html',rows=rows,indicadores=stats,grupos=groups,totais=totals)


@bp.get('/configuracao-estoque')
def configuracao():
    svc.permitir('GESTOR')
    return render('estoque_configuracao.html',usuarios=db.session.scalars(select(Usuario).order_by(Usuario.login)).all(),papeis={p.usuario_id:p.papel for p in db.session.scalars(select(PapelEstoque))},policy=db.session.get(PoliticaEstoque,1),importacoes=db.session.scalars(select(ImportacaoEstoque).order_by(ImportacaoEstoque.id.desc()).limit(30)).all())


@bp.post('/configuracao-estoque')
@mutacao('GESTOR')
def salvar_configuracao():
    kind=request.form.get('tipo')
    if kind=='unidade':
        row=svc.unidade(request.form.get('nome')); svc.auditar(None,'CADASTRO DE UNIDADE',novo=dict(id=row.id,nome=row.nome))
    elif kind=='local':
        group=svc.local(request.form.get('grupo'))
        name=request.form.get('nome','').strip()
        if not name or len(name)>100:raise ValueError('Nome de localização inválido.')
        row=LocalEstoque(codigo='LOCAL_'+secrets.token_hex(6).upper(),nome=name,grupo=group.grupo,fisica=group.fisica)
        db.session.add(row);svc.auditar(None,'CADASTRO DE LOCALIZAÇÃO',novo=dict(nome=name,grupo=group.grupo))
    elif kind=='politica':
        a=int(request.form.get('recente_dias','7')); b=int(request.form.get('vencida_dias','30'))
        if not 0<=a<b<=365:raise ValueError('Use 0 ≤ recente < vencida ≤ 365 dias.')
        p=db.session.get(PoliticaEstoque,1);before=dict(recente=p.recente_dias,vencida=p.vencida_dias);p.recente_dias=a;p.vencida_dias=b
        svc.auditar(None,'POLÍTICA DE CONFERÊNCIA',before,novo=dict(recente=a,vencida=b))
    elif kind=='papel':
        svc.permitir('ADMIN'); uid=int(request.form['usuario_id']); role=request.form.get('papel')
        if role not in svc.RANK or not db.session.get(Usuario,uid) or uid==1:raise ValueError('Usuário ou papel inválido. A administração principal é preservada.')
        p=db.session.get(PapelEstoque,uid); before=dict(usuario_id=uid,papel=p.papel if p else 'OPERADOR')
        if p is None:p=PapelEstoque(usuario_id=uid);db.session.add(p)
        p.papel=role;svc.auditar(None,'PERMISSÃO DE ESTOQUE',before,novo=dict(usuario_id=uid,papel=role))
    else:raise ValueError('Configuração inválida.')
    flash('Configuração salva com auditoria.','success')
    return redirect(url_for('inventario.configuracao'))


@bp.get('/backup-migracao')
def backup_migracao():
    svc.permitir('ADMIN')
    from schema_inventario import backup_logico
    return send_file(io.BytesIO(zlib.decompress(backup_logico())),as_attachment=True,download_name='fontes_patio_antes_inventario.json',mimetype='application/json')
