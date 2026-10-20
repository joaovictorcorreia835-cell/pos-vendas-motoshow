"""Login obrigatório, credenciais com hash e bloqueio persistido no banco."""
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from flask import request, session, redirect, url_for, render_template, jsonify, abort, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Usuario


def configure_auth(app):
    with app.app_context():
        name=os.environ.get('ADMIN_USERNAME','admin').strip().lower()
        password=os.environ.get('ADMIN_PASSWORD')
        if password and not db.session.scalar(db.select(Usuario.id)):
            if len(password)<12:
                raise RuntimeError('A senha inicial deve ter pelo menos 12 caracteres.')
            db.session.add(Usuario(login=name,senha_hash=generate_password_hash(password)))
            db.session.commit()

    @app.before_request
    def require_login():
        session.setdefault('csrf',secrets.token_hex(24))
        g.usuario=db.session.get(Usuario,session.get('usuario_id')) if session.get('usuario_id') else None
        if g.usuario and session.get('usuario_versao')!=g.usuario.versao:
            g.usuario=None
            session.clear()
        if request.endpoint in ['login','static','healthz']:
            return
        if not g.usuario:
            if request.path.startswith('/api/'):
                return jsonify(error='Faça login para acessar o sistema.'),401
            if request.method!='GET':
                abort(400,description='Faça login e recarregue o formulário.')
            return redirect(url_for('login',next=request.full_path))

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Referrer-Policy']='same-origin'
        if request.endpoint!='static':
            response.headers['Cache-Control']='no-store'
        if app.config['SESSION_COOKIE_SECURE']:
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.route('/login',methods=['GET','POST'])
    def login():
        error=None
        if request.method=='POST':
            name=request.form.get('usuario','').strip().lower()
            user=db.session.scalar(db.select(Usuario).where(Usuario.login==name).with_for_update())
            now=datetime.utcnow()
            blocked=user and user.bloqueado_ate and user.bloqueado_ate>now
            valid=check_password_hash(user.senha_hash if user else app.config['DUMMY_PASSWORD_HASH'],request.form.get('senha',''))
            if user and valid and not blocked:
                user.tentativas=0; user.bloqueado_ate=None; db.session.commit()
                session.clear(); session.permanent=True
                session.update(usuario_id=user.id,usuario_versao=user.versao,csrf=secrets.token_hex(24))
                target=request.args.get('next','/')
                parsed=urlsplit(target)
                if parsed.scheme or parsed.netloc or not target.startswith('/') or target.startswith('//') or '\\' in target:
                    target='/'
                return redirect(target)
            if user and not blocked:
                user.tentativas+=1
                if user.tentativas>=5:
                    user.bloqueado_ate=now+timedelta(minutes=15); user.tentativas=0
                db.session.commit()
            error='Usuário ou senha inválidos. Após várias tentativas, aguarde 15 minutos.'
        return render_template('login.html',error=error),401 if error else 200

    app.config['DUMMY_PASSWORD_HASH']=generate_password_hash(secrets.token_urlsafe(24))

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/minha-senha',methods=['GET','POST'])
    def minha_senha():
        if request.method=='POST':
            password=request.form.get('nova','')
            if not check_password_hash(g.usuario.senha_hash,request.form.get('atual','')):
                flash('Senha atual inválida.','danger')
            elif len(password)<12 or password!=request.form.get('confirmar'):
                flash('Use pelo menos 12 caracteres e repita a nova senha.','danger')
            else:
                g.usuario.senha_hash=generate_password_hash(password); g.usuario.versao+=1
                db.session.commit(); session.clear()
                return redirect(url_for('login'))
        return render_template('senha.html',page='configuracoes')
