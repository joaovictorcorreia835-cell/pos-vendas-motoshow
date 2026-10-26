import os, re, io, secrets, sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session, abort
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from carregamento import atendimentos
from models import *

ROOT = Path(__file__).resolve().parent
TIPOS = ['Troca de óleo','Revisão','Manutenção','Garantia','Seguro','Balcão','Outros']
STATUS = ['Aberta','Em andamento','Aguardando peças','Aguardando aprovação','Pronta','Atrasada','Finalizada','Cancelada']
CATEGORIAS = ['Peças (Balcão)','Mão de obra','Óleos e lubrificantes','Acessórios','Pneus','Outros']
MENUS = [('patio','◇','Motos no Pátio'),('dashboard','⌂','Visão Geral'),('ordens','▤','Ordens de Serviço'),('passagens','♧','Passagens'),('faturamento','▥','Faturamento'),('pedidos','▤','Pedidos em Aberto'),('pecas','◇','Peças (Balcão)'),('garantia','✚','Garantia'),('seguro','⬟','Seguro'),('clientes','♙','Clientes'),('relatorios','▧','Relatórios'),('configuracoes','⚙','Configurações')]
def create_app(database=None):
    app=Flask(__name__)
    Path(app.instance_path).mkdir(exist_ok=True)
    key=Path(app.instance_path)/'.secret'
    production=os.environ.get('APP_ENV')=='production'
    if production and (not os.environ.get('SECRET_KEY') or not os.environ.get('DATABASE_URL')):
        raise RuntimeError('Configure SECRET_KEY e DATABASE_URL para publicar o sistema.')
    if not key.exists(): key.write_text(secrets.token_hex(32))
    from deployment import database_uri
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or key.read_text(), SQLALCHEMY_DATABASE_URI=database_uri(database or os.environ.get('DATABASE_URL') or 'sqlite:///'+str(Path(app.instance_path)/'oficina.db')), MAX_CONTENT_LENGTH=25*1024*1024,
        SESSION_COOKIE_SECURE=production, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping':True})
    if production:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)
    db.init_app(app)
    from patio import bp as patio_bp
    app.register_blueprint(patio_bp)
    from inventario import bp as inventario_bp
    app.register_blueprint(inventario_bp)
    from faturamento import bp as faturamento_bp
    app.register_blueprint(faturamento_bp)
    from pedidos import bp as pedidos_bp
    app.register_blueprint(pedidos_bp)
    with app.app_context():
        from schema_inventario import preparar_backup
        preparar_backup()
        db.create_all()
        from schema_usuarios import atualizar_schema as atualizar_schema_usuarios
        atualizar_schema_usuarios()
        from schema_inventario import atualizar_schema as atualizar_schema_inventario
        atualizar_schema_inventario()
        from schema_mensal import atualizar_schema_mensal
        atualizar_schema_mensal()
        if not db.session.get(Configuracao,1): db.session.add(Configuracao(id=1,unidade='Parauapebas')); db.session.commit()
    from auth import configure_auth
    configure_auth(app)
    with app.app_context():
        from jobs_relatorios import executar_pendente
        executar_pendente()
        from jobs_patio import executar_pendente as importar_patio_pendente
        importar_patio_pendente()
        from inventario_service import sincronizar_fontes
        from schema_inventario import finalizar
        sincronizar_fontes()
        finalizar()
        db.session.commit()
        if production:
            from inventario_service import indicadores as indicadores_estoque
            from schema_inventario import versoes, VERSAO
            import json
            check=db.session.execute(db.select(versoes.c.status,versoes.c.sha256).where(versoes.c.versao==VERSAO)).one()
            print('INVENTARIO_PRONTO '+json.dumps(dict(migracao=check.status,backup_sha256=check.sha256,**indicadores_estoque())),flush=True)
    @app.get('/atualizacoes/backup/<digest>')
    def backup_relatorios(digest):
        from jobs_relatorios import historico
        from sqlalchemy import inspect
        if not re.fullmatch(r'[a-f0-9]{64}',digest) or not inspect(db.engine).has_table(historico.name):abort(404)
        data=db.session.execute(db.select(historico.c.backup).where(historico.c.sha256==digest)).scalar()
        if data is None:abort(404)
        return send_file(io.BytesIO(data),as_attachment=True,download_name='antes_atualizacao_'+digest[:12]+'.db')
    @app.context_processor
    def server_context():
        return {'config_online':db.engine.dialect.name!='sqlite'}
    @app.get('/healthz')
    def healthz():
        db.session.execute(db.text('SELECT 1'))
        return jsonify(status='ok')
    @app.post('/importacao-inicial')
    def importacao_inicial():
        if os.environ.get('ALLOW_INITIAL_IMPORT')!='true': abort(404)
        uploaded=request.files.get('arquivo')
        if not uploaded: return jsonify(error='Selecione o backup inicial.'),400
        from sqlalchemy import create_engine
        from deployment import copy_database
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'origem.db'
            uploaded.save(path)
            source=create_engine('sqlite:///file:'+path.as_posix()+'?mode=ro&uri=true')
            try:
                db.session.remove()
                copy_database(source,db.engine,allow_config=True,exclude_auth=True)
            except Exception:
                db.session.rollback()
                return jsonify(error='Importação recusada: verifique se o backup é compatível e o destino está vazio.'),409
            finally: source.dispose()
        return jsonify(status='ok',mensagem='Dados importados e valores conferidos.')
    @app.template_filter('brl')
    def brl(n): return 'R$ '+f'{(n or 0)/100:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    @app.template_filter('cpf_format')
    def cpf_format(value):
        n=re.sub(r'\D','',value or '')
        return f'{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}' if len(n)==11 else n
    @app.template_filter('phone_format')
    def phone_format(value):
        n=re.sub(r'\D','',value or '')
        return f'({n[:2]}) {n[2:-4]}-{n[-4:]}' if len(n) in [10,11] else n
    @app.context_processor
    def context():
        from inventario_models import UnidadeEstoque
        session.setdefault('csrf',secrets.token_hex(24))
        from estoque_acesso import exclusivo, unidade_usuario
        if exclusivo():
            from types import SimpleNamespace
            unit=unidade_usuario()
            return dict(menus=[],tipos=[],statuses=[],categorias=[],consultores=[],mecanicos=[],consultores_mensais=[],unidades=[unit.nome],config=SimpleNamespace(unidade=unit.nome),csrf=session['csrf'])
        return dict(menus=MENUS,tipos=TIPOS,statuses=STATUS,categorias=CATEGORIAS,consultores=db.session.scalars(db.select(Consultor)).all(),mecanicos=db.session.scalars(db.select(Mecanico)).all(),config=db.session.get(Configuracao,1),consultores_mensais=db.session.execute(db.select(FaturamentoConsultor.codigo,FaturamentoConsultor.nome).distinct()).all(),unidades=sorted(set(db.session.scalars(db.select(Passagem.unidade).distinct()).all()+db.session.scalars(db.select(FaturamentoMensal.unidade).distinct()).all()+db.session.scalars(db.select(Pedido.unidade).distinct()).all()+db.session.scalars(db.select(UnidadeEstoque.nome)).all()+[db.session.get(Configuracao,1).unidade])),csrf=session['csrf'])
    from indicadores import prazo
    app.jinja_env.globals['prazo_registro']=prazo
    @app.before_request
    def csrf_check():
        if request.method=='POST' and (not session.get('csrf') or not secrets.compare_digest(request.form.get('csrf',''),session['csrf'])): abort(400,description='Formulário expirado. Recarregue a página.')
    def dates(args):
        today=date.today(); period=args.get('periodo','hoje')
        if args.get('inicio'): return date.fromisoformat(args['inicio']),date.fromisoformat(args.get('fim') or args['inicio'])
        if period=='ontem': return today-timedelta(days=1),today-timedelta(days=1)
        if period=='semana': return today-timedelta(days=today.weekday()),today
        if period=='mes': return today.replace(day=1),today
        if period=='anterior':
            end=today.replace(day=1)-timedelta(days=1); return end.replace(day=1),end
        return today,today
    def records(args=None,por_entrada=True):
        args=request.args if args is None else args
        start,end=dates(args)
        q=db.select(Passagem).options(*atendimentos())
        if por_entrada:q=q.where(Passagem.data>=datetime.combine(start,datetime.min.time()),Passagem.data<datetime.combine(end+timedelta(days=1),datetime.min.time()))
        for key,col in [('tipo',Passagem.tipo),('status',Passagem.status),('unidade',Passagem.unidade),('consultor',Passagem.consultor_id),('mecanico',Passagem.mecanico_id)]:
            if args.get(key):
                value=args[key]
                if key=='consultor' and value.startswith('mensal:'):
                    names=db.session.scalars(db.select(FaturamentoConsultor.nome).where(FaturamentoConsultor.codigo==value[7:])).all()
                    q=q.where(Passagem.consultor_id.in_(db.select(Consultor.id).where(db.func.lower(Consultor.nome).in_([n.lower() for n in names]))))
                else: q=q.where(col==value)
        return db.session.scalars(q.order_by(Passagem.data.desc())).all()
    def live(rows): return [p for p in rows if p.status!='Cancelada']
    def revenue(p): return p.total if p.status!='Cancelada' and (p.ordem or p.tipo=='Balcão') else 0
    def metrics(rows):
        valid=live(rows); billed=[p for p in valid if p.ordem or p.tipo=='Balcão']
        return [len([p for p in valid if p.tipo!='Balcão']),sum(revenue(p) for p in valid),sum(revenue(p) for p in valid if p.ordem and p.tipo!='Balcão'),sum(revenue(p) for p in valid if p.tipo=='Balcão'),sum(i.valor_liquido for p in billed for i in p.itens if i.categoria=='Mão de obra'),len([p for p in valid if p.ordem and p.status!='Finalizada']),len([p for p in valid if p.garantia]),len([p for p in valid if p.seguro])]
    @app.get('/')
    def dashboard():
        args=dict(request.args); args.setdefault('periodo','mes')
        result=dashboard_data(args)
        if isinstance(result,tuple):
            flash(result[0].get_json()['error'],'danger')
            result=dashboard_data({'periodo':'mes'})
        return render_template('dashboard.html',page='dashboard',default_period='mes',initial=result.get_json())
    @app.get('/api/dashboard')
    def dashboard_data(args=None):
        args=request.args if args is None else args
        try: rows=records(args); start,end=dates(args)
        except ValueError: return jsonify(error='Período inválido'),400
        if end<start or (end-start).days>366: return jsonify(error='Selecione um período de até 367 dias.'),400
        previous=dict(args); previous['inicio']=(start-(end-start)-timedelta(days=1)).isoformat(); previous['fim']=(start-timedelta(days=1)).isoformat()
        totals=metrics(rows); prev=metrics(records(previous)); valid=live(rows)
        chartstart=start if start!=end else end-timedelta(days=6)
        chartargs=dict(args); chartargs.update(inicio=chartstart.isoformat(),fim=end.isoformat())
        chartrows=live(records(chartargs)); days=[chartstart+timedelta(days=i) for i in range((end-chartstart).days+1)]
        series=[]
        for kind in ['os','balcao','mao']:
            values=[]
            for day in days:
                ps=[p for p in chartrows if p.data.date()==day]
                if kind=='os': value=sum(i.valor_liquido for p in ps if p.ordem and p.tipo!='Balcão' for i in p.itens if i.categoria!='Mão de obra')
                elif kind=='balcao': value=sum(revenue(p) for p in ps if p.tipo=='Balcão')
                else: value=sum(i.valor_liquido for p in ps if p.ordem and p.tipo!='Balcão' for i in p.itens if i.categoria=='Mão de obra')
                values.append(value/100)
            series.append(values)
        from dashboard_finance import financials
        from faturamento import shift
        finance=financials(start,end,args,rows)
        totals[1:5]=finance['sums']
        # Para consolidados, a compara??o financeira usa meses de calend?rio.
        if finance['monthly']:
            count=len(finance['months']); first=shift(start.year,start.month,-count)
            last=shift(start.year,start.month,-1); after=shift(*last,1)
            pstart=date(*first,1); pend=date(*after,1)-timedelta(days=1)
            pargs=dict(args); pargs.update(inicio=pstart.isoformat(),fim=pend.isoformat())
            previous_finance=financials(pstart,pend,pargs,records(pargs))
            prev[1:5]=previous_finance['sums']
            if not previous_finance['monthly'] and not any(previous_finance['sums']): prev[1:5]=[None]*4
            days=[date(y,m,1) for y,m in finance['months']]
            series=[[finance['series'][(d.year,d.month)][i]/100 for d in days] for i in range(3)]
        else:
            pstart,pend=dates(previous)
            prev[1:5]=financials(pstart,pend,previous,records(previous))['sums']
        def row(p): return dict(prazo=prazo(p.data,bool(p.ordem and p.status not in ['Finalizada','Cancelada'])),id=p.id,hora=p.data.strftime('%H:%M'),data=p.data.strftime('%d/%m/%Y'),cliente=p.cliente.nome,moto=p.modelo,placa=p.placa,consultor=p.consultor.nome if p.consultor else '',tipo=p.tipo,status=p.status,os=p.ordem.numero if p.ordem else '',valor=brl(revenue(p)))
        osrows=[p for p in valid if p.ordem and p.status!='Finalizada']
        from pedidos import dashboard_data as pedidos_data
        pedidos_summary=pedidos_data(args,datetime.combine(start,datetime.min.time()),datetime.combine(end+timedelta(days=1),datetime.min.time()),brl)
        pending_finance=dict(os_centavos=sum(p.total for p in osrows),pedidos_centavos=pedidos_summary['total_centavos'])
        pending_finance['total_centavos']=pending_finance['os_centavos']+pending_finance['pedidos_centavos']
        from indicadores import ticket_medio,ticket_pedidos_faturados
        from indicadores import faturada_no_periodo
        ticket=ticket_medio([p for p in records(args,por_entrada=False) if faturada_no_periodo(p,start,end)])
        from indicadores import resumo_prazos
        from pedidos import filtered as pedidos_filtered
        backlog_args=dict(args);backlog_args.update(inicio='1900-01-01',fim=date.today().isoformat())
        backlog_os=[p for p in records(backlog_args) if p.ordem and p.status not in ['Finalizada','Cancelada']]
        backlog_pedidos=db.session.scalars(pedidos_filtered(args).where(Pedido.status=='Aberto')).all()
        alertas=dict(os=resumo_prazos(backlog_os,'data'),pedidos=resumo_prazos(backlog_pedidos,'inserido_em'))
        payload=dict(ticket_pedidos_faturados=ticket_pedidos_faturados(rows),alertas_prazo=alertas,ticket_medio=ticket,faturamento_pendente=pending_finance,range=dict(inicio=start.isoformat(),fim=end.isoformat()),pedidos=pedidos_summary,totals=totals,previous=prev,days=[d.strftime('%m/%Y' if finance['monthly'] else '%d/%m') for d in days],series=series,financial_monthly=finance['monthly'],financial_note=('Faturamento da planilha mensal. O consolidado substitui as OS da mesma unidade e mês; não há duplicação. Passagens e status continuam vindo dos atendimentos.' if finance['monthly'] else 'Consolidado mensal disponível: selecione Este mês, Mês anterior ou um intervalo começando no dia 1, sem filtro de tipo ou status.' if finance['saved'] else ''),category_labels=CATEGORIAS+(['OS (Serviços)'] if finance['monthly'] else []),types=[sum((p.tipo==t or (t=='Manutenção' and p.tipo=='Troca de óleo')) for p in valid if p.tipo!='Balcão') for t in ['Revisão','Manutenção','Garantia','Seguro','Outros']],statuses=[sum(p.status==s or (s=='Em andamento' and p.status=='Aberta') for p in osrows) for s in ['Em andamento','Aguardando peças','Aguardando aprovação','Pronta','Atrasada']],categories=finance['categories'] if finance['monthly'] else finance['categories'][:6],passagens=[row(p) for p in valid if p.tipo!='Balcão'][:6],ordens=[row(p) for p in osrows][:6])
        deadline_links={}
        for group in ['os','pedidos']:
            deadline_links[group]={}
            for level in ['atencao','atrasado']:
                query={k:args[k] for k in ['unidade','consultor'] if args.get(k)}
                query['prazo']=level
                if group=='os':
                    query.update(periodo='custom',inicio='1900-01-01',fim=date.today().isoformat())
                    query.update({k:args[k] for k in ['tipo','status'] if args.get(k)})
                    deadline_links[group][level]=url_for('listagem',page='ordens',**query)
                else:
                    deadline_links[group][level]=url_for('pedidos.listagem',**query)
        payload['deadline_links']=deadline_links
        from patio import resumo_atrasadas
        payload['patio_atrasadas']=resumo_atrasadas(args.get('unidade',''))
        from graficos import graficos_painel
        payload['charts']=graficos_painel(payload)
        return jsonify(payload)
    @app.route('/lancamento',methods=['GET','POST'])
    @app.route('/lancamento/<int:ident>',methods=['GET','POST'])
    def lancamento(ident=None):
        p=db.get_or_404(Passagem,ident) if ident else None
        if request.method=='POST':
            f=request.form
            try:
                nome=f.get('cliente','').strip(); tipo=f.get('tipo'); status=f.get('status')
                if not nome or tipo not in TIPOS or status not in STATUS: raise ValueError('Informe cliente, tipo e status válidos.')
                if p and p.venda_balcao and tipo!='Balc\u00e3o': raise ValueError('Mantenha o tipo de um documento de balc\u00e3o importado.')
                moment=datetime.fromisoformat(f['data']+'T'+f['hora'])
                if not f.get('unidade','').strip(): raise ValueError('Informe a unidade.')
                km=int(f.get('km') or 0)
                if km<0: raise ValueError('Quilometragem não pode ser negativa.')
                amounts=[]
                for index,c in enumerate(CATEGORIAS):
                    value=Decimal(f.get('valor'+str(index),'0').replace(',','.') or '0')
                    if not value.is_finite() or value<0 or value>Decimal('999999999'): raise ValueError('Valor inválido ou negativo.')
                    amounts.append(int(value.quantize(Decimal('.01'))*100))
                numero=f.get('os','').strip()
                if not numero and tipo!='Balcão' and sum(amounts): raise ValueError('Passagem sem OS não pode ter faturamento. Informe a OS ou selecione Balcão.')
                cpf=re.sub(r'\D','',f.get('cpf','')) or None
                if cpf and len(cpf)!=11: raise ValueError('CPF deve ter 11 dígitos.')
                cid=f.get('cliente_id')
                client=db.session.get(Cliente,int(cid)) if cid else None
                if not client and cpf: client=db.session.scalar(db.select(Cliente).where(Cliente.cpf==cpf))
                phone=re.sub(r'\D','',f.get('telefone',''))
                if not client: client=db.session.scalar(db.select(Cliente).where(Cliente.nome==nome,Cliente.telefone==phone)) if phone else None
                if not client: client=Cliente(nome=nome); db.session.add(client)
                client.nome=nome; client.cpf=cpf; client.telefone=phone
                for key in ['modelo','ano','chassi']: setattr(client,key,f.get(key,''))
                client.placa=f.get('placa','').upper().replace('-','').strip(); client.moto=f.get('modelo','')
                db.session.flush()
                if not p: p=Passagem(); db.session.add(p)
                p.cliente=client; p.data=moment; p.tipo=tipo; p.status=status; p.unidade=f['unidade'].strip(); p.km=km
                for key in ['modelo','ano','placa']: setattr(p,key,getattr(client,key))
                for key,cls in [('consultor',Consultor),('mecanico',Mecanico)]:
                    name=f.get(key,'').strip(); person=db.session.scalar(db.select(cls).where(cls.nome==name)) if name else None
                    if name and not person: person=cls(nome=name); db.session.add(person)
                    setattr(p,key,person)
                if numero:
                    if not p.ordem: p.ordem=OrdemServico(numero=numero)
                    else: p.ordem.numero=numero
                else: p.ordem=None
                p.itens.clear()
                for c,amount in zip(CATEGORIAS,amounts): p.itens.append(ItemOrdem(categoria=c,centavos=amount))
                p.garantia=p.garantia or Garantia() if tipo=='Garantia' else None
                p.seguro=p.seguro or Seguro() if tipo=='Seguro' else None
                if p.garantia:
                    p.garantia.tipo=f.get('garantia_tipo',''); p.garantia.descricao=f.get('descricao',''); p.garantia.status=f.get('especial_status','Aberta')
                    if p.garantia.status not in ['Aberta','Em análise','Aprovada','Reprovada','Finalizada']: raise ValueError('Status de garantia inválido.')
                if p.seguro:
                    p.seguro.seguradora=f.get('seguradora',''); p.seguro.sinistro=f.get('sinistro',''); p.seguro.descricao=f.get('descricao',''); p.seguro.status=f.get('especial_status','Aberta')
                db.session.commit(); flash('Lançamento salvo. Indicadores atualizados.','success'); return redirect(url_for('dashboard'))
            except (ValueError,InvalidOperation,KeyError) as e: db.session.rollback(); flash(str(e),'danger')
            except IntegrityError: db.session.rollback(); flash('Número de OS ou CPF já cadastrado.','danger')
        return render_template('lancamento.html',p=p,page='lancamento',now=datetime.now(),clientes=db.session.scalars(db.select(Cliente).order_by(Cliente.nome)).all())
    @app.post('/excluir/<int:ident>')
    def excluir(ident):
        db.session.delete(db.get_or_404(Passagem,ident)); db.session.commit(); flash('Lançamento excluído.','success'); return redirect(url_for('listagem',page='passagens'))
    @app.route('/clientes',methods=['GET','POST'])
    def clientes():
        if request.method=='POST':
            try:
                f=request.form; c=db.session.get(Cliente,int(f['id'])) if f.get('id') else Cliente()
                if not f.get('nome','').strip(): raise ValueError('Nome obrigatório.')
                for k in ['nome','telefone','moto','modelo','ano','placa','chassi']: setattr(c,k,f.get(k,'').strip())
                c.telefone=re.sub(r'\D','',c.telefone); c.placa=c.placa.upper().replace('-','')
                c.cpf=re.sub(r'\D','',f.get('cpf','')) or None
                if c.cpf and len(c.cpf)!=11: raise ValueError('CPF deve ter 11 dígitos.')
                db.session.add(c); db.session.commit(); flash('Cliente salvo.','success')
            except (ValueError,IntegrityError) as e: db.session.rollback(); flash('Dados inválidos ou CPF duplicado: '+str(e).split('\n')[0][:100],'danger')
            return redirect(url_for('clientes'))
        cs=db.session.scalars(db.select(Cliente).order_by(Cliente.nome)).all()
        selected=db.session.get(Cliente,request.args.get('id',type=int)) if request.args.get('id') else None
        history=db.session.scalars(db.select(Passagem).options(*atendimentos()).where(Passagem.cliente_id==selected.id).order_by(Passagem.data.desc())).all() if selected else []
        return render_template('clientes.html',page='clientes',clientes=cs,selected=selected,history=history,total=sum(revenue(p) for p in history))
    @app.post('/clientes/<int:ident>/excluir')
    def excluir_cliente(ident):
        c=db.get_or_404(Cliente,ident)
        if db.session.scalar(db.select(Passagem).where(Passagem.cliente_id==ident)): flash('Cliente possui histórico. Exclua os lançamentos antes.','danger')
        else: db.session.delete(c); db.session.commit(); flash('Cliente excluído.','success')
        return redirect(url_for('clientes'))
    def report_rows(rows,kind):
        if kind in ['diario','mensal','consultor','mecanico']:
            groups={}
            for p in rows:
                key=p.data.strftime('%Y-%m' if kind=='mensal' else '%d/%m/%Y') if kind in ['diario','mensal'] else (getattr(p,kind).nome if getattr(p,kind) else 'Não informado')
                count,value=groups.get(key,(0,0)); groups[key]=(count+1,value+revenue(p))
            return ['Grupo','Atendimentos','Faturamento'],[[k,n,brl(v)] for k,(n,v) in sorted(groups.items())]
        if kind=='abertas': rows=[p for p in rows if p.ordem and p.status not in ['Finalizada','Cancelada']]
        if kind=='garantias': rows=[p for p in rows if p.garantia]
        if kind=='seguros': rows=[p for p in rows if p.seguro]
        if kind=='passagens': rows=[p for p in rows if p.tipo!='Balcão']
        if kind in ['pecas','mao']:
            cats=CATEGORIAS[:1]+CATEGORIAS[2:] if kind=='pecas' else ['Mão de obra']
            return ['Data','Cliente','OS','Categoria','Valor'],[[p.data.strftime('%d/%m/%Y'),p.cliente.nome,p.ordem.numero if p.ordem else 'Balcão',i.categoria,brl(i.valor_liquido)] for p in live(rows) if p.ordem or p.tipo=='Balcão' for i in p.itens if i.categoria in cats and i.centavos]
        return ['Data','Cliente','OS','Tipo','Status','Valor'],[[p.data.strftime('%d/%m/%Y'),p.cliente.nome,p.ordem.numero if p.ordem else '—',p.tipo,p.status,brl(revenue(p))] for p in rows]
    @app.get('/relatorios')
    def relatorios():
        try: rows=records()
        except ValueError: flash('Período inválido.','danger'); rows=[]
        kind=request.args.get('relatorio','diario'); headers,data=report_rows(rows,kind)
        export=request.args.get('export')
        if export=='xlsx':
            from openpyxl import Workbook
            wb=Workbook(); ws=wb.active; ws.title='Relatório'; ws.append(headers)
            for row in data: ws.append(row)
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width=28
            stream=io.BytesIO(); wb.save(stream); stream.seek(0)
            return send_file(stream,download_name='relatorio_oficina.xlsx',as_attachment=True)
        if export=='pdf':
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.pagesizes import landscape,A4
            from xml.sax.saxutils import escape
            stream=io.BytesIO(); doc=SimpleDocTemplate(stream,pagesize=landscape(A4),rightMargin=25,leftMargin=25)
            style=getSampleStyleSheet(); table=Table([[Paragraph(escape(str(v)),style['BodyText']) for v in r] for r in [headers]+data],repeatRows=1,colWidths=[740/len(headers)]*len(headers))
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightblue),('GRID',(0,0),(-1,-1),.3,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP')]))
            doc.build([Paragraph('MOTOSHOW — Relatório de oficina',style['Title']),Spacer(1,15),table]); stream.seek(0)
            return send_file(stream,download_name='relatorio_oficina.pdf',as_attachment=True)
        return render_template('relatorios.html',page='relatorios',headers=headers,data=data)
    @app.route('/configuracoes',methods=['GET','POST'])
    def configuracoes():
        if request.method=='POST':
            name=request.form.get('nome','').strip(); kind=request.form.get('kind')
            if name:
                try:
                    if kind=='unidade': db.session.get(Configuracao,1).unidade=name
                    elif kind in ['consultor','mecanico']: db.session.add((Consultor if kind=='consultor' else Mecanico)(nome=name))
                    db.session.commit(); flash('Configuração salva.','success')
                except IntegrityError: db.session.rollback(); flash('Nome já cadastrado.','danger')
            return redirect(url_for('configuracoes'))
        return render_template('configuracoes.html',page='configuracoes')
    def backup_file():
        folder=ROOT/'backups'; folder.mkdir(exist_ok=True)
        path=folder/datetime.now().strftime('backup_oficina_%Y-%m-%d_%H-%M-%S-%f.db')
        with closing(sqlite3.connect(db.engine.url.database)) as source,closing(sqlite3.connect(path)) as dest: source.backup(dest)
        return path
    @app.post('/backup')
    def backup():
        if db.engine.dialect.name!='sqlite':
            from deployment import sqlite_snapshot
            stream=sqlite_snapshot(db.engine)
            return send_file(stream,download_name='backup_oficina.db',as_attachment=True)
        return send_file(backup_file(),as_attachment=True)
    @app.post('/restaurar')
    def restaurar():
        if db.engine.dialect.name!='sqlite':
            flash('No servidor, a restauração deve ser feita pelo administrador a partir de um backup validado.','warning')
            return redirect(url_for('configuracoes'))
        uploaded=request.files.get('arquivo')
        if not uploaded or request.form.get('confirmar')!='SIM': flash('Selecione um backup e confirme a substituição.','danger'); return redirect(url_for('configuracoes'))
        temp=Path(app.instance_path)/('restore-'+secrets.token_hex(8)+'.db')
        try:
            uploaded.save(temp)
            with closing(sqlite3.connect(temp)) as con:
                if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Banco corrompido.')
                expected={t.name:set(c.name for c in t.columns) for t in db.metadata.sorted_tables}
                for table,cols in expected.items():
                    actual={r[1] for r in con.execute('PRAGMA table_info("'+table+'")')}
                    if not cols<=actual: raise ValueError('Backup incompatível com esta versão.')
                if con.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Relacionamentos inválidos no backup.')
            backup_file(); db.session.remove(); db.engine.dispose()
            with closing(sqlite3.connect(temp)) as source,closing(sqlite3.connect(db.engine.url.database)) as dest: source.backup(dest)
            flash('Backup restaurado. Cópia anterior preservada em backups/.','success')
        except (sqlite3.Error,ValueError) as e: flash('Restauração recusada: '+str(e),'danger')
        finally: temp.unlink(missing_ok=True)
        return redirect(url_for('configuracoes'))
    @app.get('/faturamento/lancamentos')
    def faturamento_lancamentos():
        return listagem('faturamento')
    @app.get('/<page>')
    def listagem(page):
        if page not in ['ordens','passagens','faturamento','pecas','garantia','seguro']: abort(404)
        try: rows=records(dict(periodo='mes',**request.args) if 'periodo' not in request.args else request.args)
        except ValueError: rows=[]; flash('Período inválido.','danger')
        if page=='ordens': rows=[p for p in rows if p.ordem]
        if page=='ordens' and request.args.get('prazo'):
            rows=[p for p in rows if prazo(p.data,p.status not in ['Finalizada','Cancelada'])['nivel']==request.args['prazo']]
        if page=='passagens': rows=[p for p in rows if p.tipo!='Balcão']
        if page=='pecas': rows=[p for p in rows if p.tipo=='Balcão']
        if page in ['garantia','seguro']: rows=[p for p in rows if getattr(p,page)]
        if page=='ordens' and request.args.get('export')=='xlsx':
            from exportacoes import export_ordens
            return export_ordens(rows,request.args.get('prazo',''))
        return render_template('listagem.html',page=page,default_period='mes',rows=rows,total=sum(revenue(p) for p in rows))
    return app
app=create_app()
if __name__=='__main__':
    import socket
    port=int(os.environ.get('OFICINA_PORT','5000'))
    while True:
        probe=socket.socket()
        try:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'): probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            probe.bind(('127.0.0.1',port))
            break
        except OSError:
            print(f'Porta {port} ocupada. Tentando {port+1}...')
            port+=1
            if port>5100: raise RuntimeError('Nenhuma porta local disponível entre 5000 e 5100.')
        finally: probe.close()
    print(f'Controle de Oficina Motoshow: http://localhost:{port}')
    app.run(host='127.0.0.1',port=port,debug=False)
