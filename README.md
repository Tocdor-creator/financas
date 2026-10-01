# 💰 Finanças da Casa

Esse é o app que eu fiz para organizar o dinheiro aqui de casa, meu e da Kauany.

A gente vivia anotando gasto em planilha, esquecendo conta para pagar e sem saber direito quanto ia sobrar no fim do mês. Então resolvi fazer um app do nosso jeito: com cara de app de banco, fácil de usar no celular e com cada um tendo o seu login, para saber quem lançou o quê.

Ele roda num celular Android aqui de casa (com Termux) e a gente acessa pelo navegador de qualquer lugar, usando o Tailscale. Nada fica em serviço de terceiros: os dados são nossos.

## O que dá para fazer

- **Início** — o saldo do mês e, logo embaixo, quanto **vai sobrar ou faltar** depois de pagar as contas que ainda estão em aberto. Tem atalhos para lançar entrada, saída, pagar conta, guardar dinheiro e importar extrato. O botão de olho no topo esconde os valores (bom para abrir o app perto dos outros).
- **Extrato** — tudo o que entrou e saiu, agrupado por dia e mês a mês, com categoria e comprovante. Tocando em qualquer lançamento dá para editar ou excluir.
- **Contas** — as contas fixas (aluguel, luz, água, internet…) cadastradas uma vez só, com dia de vencimento e quem paga. Todo mês elas aparecem de novo, avisando o que venceu ou vence em breve. Ao pagar, o lançamento vai sozinho para o extrato, com o comprovante se eu quiser anexar.
- **Caixinhas** — o dinheiro guardado para cada sonho: viagem, reserva de emergência, carro… Cada caixinha tem foto, meta e barra de progresso. Também mostra a Selic e o CDI do momento (via Banco Central).
- **Previsão x Realizado** — a gente define quanto planeja gastar e ganhar no mês e compara com o que aconteceu de verdade.
- **Importar PDF** — mando o extrato do banco ou a fatura do cartão, confiro numa tela de revisão e salvo tudo de uma vez. O app aprende as categorias: marcou "Supermercado XYZ" como Mercado uma vez, da próxima já vem sugerido.
- **Perfil** — cada um troca a própria senha e escolhe a cor do app e o fundo da tela. Também tem um botão para baixar o backup.

Outras coisinhas: login com bloqueio depois de 5 senhas erradas, valores e datas no formato brasileiro (R$ 1.234,56 · 27/09) e layout pensado primeiro para o celular.

## Como é feito

- **Python + Flask** no back-end, com páginas em HTML (Jinja) e CSS próprio, sem framework de front.
- **SQLite** como banco (um arquivo só, `financas.db`).
- **pdfplumber** para ler os PDFs dos bancos.
- **Chart.js** para os gráficos.

```
app.py              tudo do back-end: rotas, banco, regras
templates/          as telas (base.html é o layout com o menu)
static/css/         o visual
servidor.sh         liga/desliga o app no servidor (Termux)
```

## Rodando no meu computador

Na primeira vez:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Depois é só abrir a pasta no VS Code e apertar **F5** (já está configurado para usar a `.venv`). Ou pelo terminal:

```
.venv\Scripts\python app.py
```

E abrir http://127.0.0.1:5000. Se o banco ainda não existir, o app pede para criar as duas contas.

## O servidor (celular com Termux)

O app oficial roda no celular, na pasta `~/financas`. Lá dentro:

```
sh servidor.sh iniciar   # liga em segundo plano
sh servidor.sh parar     # desliga
sh servidor.sh status    # está rodando?
sh servidor.sh log       # últimas linhas do log
```

Pelo Tailscale, a gente acessa `http://<ip-do-celular-no-tailscale>:5000` de qualquer lugar. Para o Android não matar o app, o Termux está sem restrição de bateria.

**Para mandar uma atualização** (só o código; o banco, as fotos e os comprovantes ficam no celular e não são sobrescritos):

```
git archive HEAD | ssh -p 8022 <ip-do-celular> "cd ~/financas && tar -xf - && sh servidor.sh parar && sh servidor.sh iniciar"
```

Antes de atualizar, eu faço um backup do `financas.db` do servidor na pasta `backups/` de lá.

> No Termux, as bibliotecas `pillow` e `cryptography` têm que vir do `pkg` (`pkg install python-pillow python-cryptography`), porque pelo `pip` elas não compilam no Android. O resto vem do `requirements.txt`.

## Onde ficam os dados

- `financas.db` — todos os lançamentos, contas, caixinhas e logins
- `comprovantes/` — os comprovantes anexados
- `sonhos/` — as fotos das caixinhas
- `secret.key` — a chave que mantém o login funcionando entre reinícios

Nada disso vai para o git (está no `.gitignore`). O lugar oficial dos dados é o servidor; no computador eu só desenvolvo e testo. De vez em quando baixo o backup pelo Perfil e guardo em outro lugar.

## Sobre a leitura de PDF

Cada banco tem um formato diferente de PDF, então o leitor procura linhas no padrão `data + descrição + valor` e não vai acertar 100% sempre. Por isso existe a tela de revisão: dá para corrigir ou desmarcar o que veio errado antes de salvar. Se a data vier sem ano (comum em fatura de cartão), ele deduz o ano certo, inclusive para fatura de dezembro importada em janeiro.

## Ideias para depois

- Avisar quando um PDF importado tiver lançamentos que já estão no app (evitar duplicados)
- Planejar meses futuros na Previsão
- Exportar para Excel
- Proteção CSRF nos formulários
- Fazer o app subir sozinho quando o celular reiniciar (Termux:Boot)
