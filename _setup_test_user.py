import sys, os, sqlite3
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'i:/Meu Drive/WEMERSON/APLICATIVOS/estoque_app')
from passlib.context import CryptContext
pwd = CryptContext(schemes=['bcrypt'], deprecated='auto', bcrypt__rounds=12)
h = pwd.hash('TesteSeg123!')
conn = sqlite3.connect('i:/Meu Drive/WEMERSON/APLICATIVOS/estoque_app/estoque.db')
conn.execute("DELETE FROM usuarios WHERE email='ci@teste.internal'")
conn.execute("INSERT INTO usuarios (nome,email,senha_hash,grupo,ativo) VALUES (?,?,?,?,?)",
             ('Teste CI', 'ci@teste.internal', h, 'mestre', 1))
conn.commit()
conn.close()
print('Usuario CI criado')
