# 💰 Finanças da Casa

App local (roda no seu computador, no navegador) para você e sua esposa organizarem entradas, saídas, contas fixas e investimentos, com login separado para cada um, dashboard com gráficos, e importação de PDF com aprendizado automático de categorias.

## Como instalar (só precisa fazer uma vez)

1. Instale o **Python 3** (se ainda não tiver): https://www.python.org/downloads/
   - No Windows, marque a opção "Add Python to PATH" durante a instalação.
2. Abra o terminal (ou Prompt de Comando) dentro desta pasta.
3. Instale as dependências:

   ```
   pip install -r requirements.txt
   ```

## Como rodar

Sempre que quiser usar o app:

```
python app.py
```

Vai aparecer uma mensagem tipo `Neste computador: http://127.0.0.1:5000`. Abra esse endereço no seu navegador.

Para parar o servidor, volte ao terminal e aperte `CTRL + C`.

> Na primeira vez que rodar, o app vai te levar direto para uma tela de configuração para criar as duas contas (a sua e a da sua esposa).

## O que o app faz

- **Login separado** — cada lançamento fica registrado com o nome de quem colocou. Limite de 5 tentativas erradas de senha (bloqueio de 15 minutos) para segurança.
- **Dashboard** — saldo do mês, gastos por categoria, evolução dos últimos 6 meses (entradas, saídas e investimentos), gasto por pessoa, comparativo de despesas fixas x entradas, e alertas de contas fixas vencidas ou a vencer nos próximos 7 dias.
- **Lançamentos** — Entradas e Saídas, com categoria livre e comprovante opcional (PDF, JPG, PNG, WEBP).
- **Contas Fixas** — cadastre uma vez (ex: Água, Luz, Aluguel), com dia de vencimento e responsável pelo pagamento (ex: "Água — Kauany", "Luz — Bruno", "Casa — Ambos"). Todo mês ela reaparece pronta para marcar como paga; ao confirmar, vira uma saída automaticamente com a data do pagamento, e você pode anexar o comprovante.
- **Investimentos** — cadastre instrumentos com nome próprio (ex: "Reserva CDI 100%", "Tesouro Selic"), lance aportes e resgates, veja o total por instrumento e a evolução no dashboard. Mostra também a taxa Selic e CDI do dia (via API pública do Banco Central, quando há internet).
- **Previsão x Realizado** — defina quanto vocês planejam gastar/ganhar por mês e compare com o que realmente aconteceu, num gráfico de 4 linhas (Gastos Planejados, Gastos Reais, Ganhos Planejados, Ganhos Reais).
- **Mural de sonhos** (dentro de Investimentos) — um painel de fotos opcional para guardar imagens do que vocês estão juntando dinheiro para conquistar.
- **Perfil** — cada pessoa pode trocar a própria senha e escolher sua paleta de cores e fundo da tela (branco, gradiente rosa, azul, lilás ou verde) — só muda a aparência para quem escolheu.
- **Importar PDF** — extrato ou fatura, com tela de revisão antes de salvar e aprendizado automático de categoria (ex: uma vez marcado "Supermercado XYZ" como Mercado, da próxima vez ele já vem sugerido).
- **Backup** — na tela de Perfil, um botão para baixar uma cópia do banco de dados (financas.db) a qualquer momento.

## Sobre a leitura de PDF

Bancos e cartões têm formatos de PDF bem diferentes entre si. O leitor tenta reconhecer linhas no formato `data + descrição + valor`. Ele não vai acertar 100% de todos os bancos — por isso a tela de revisão existe: você confere, corrige o que precisar (ou desmarca a linha) e só depois confirma. Linhas com data ou valor inválido são simplesmente ignoradas (com um aviso), sem travar a importação das demais. Se um PDF específico não for bem reconhecido, me mostre um exemplo (sem dados sensíveis) que eu ajusto o leitor para ele.

## Acessando de outros aparelhos (celular, notebook da esposa, etc) — mesma Wi-Fi

O app já está configurado para escutar na rede local.

**Descobrir o IP local:**

- **Windows**: Prompt de Comando → `ipconfig` → procure "Endereço IPv4".
- **Mac**: Preferências do Sistema → Rede → Wi-Fi. Ou no terminal: `ipconfig getifaddr en0`.
- **Linux**: no terminal, `hostname -I`.

Com o app rodando, em qualquer aparelho na mesma Wi-Fi, abra `http://SEU-IP-LOCAL:5000` (ex: `http://192.168.0.15:5000`).

Se não conseguir acessar: confirme que ambos estão na mesma rede, e libere o Python no Firewall do Windows (Configurações → Privacidade e segurança → Firewall e proteção de rede → Permitir um aplicativo pelo firewall → Python, marcando "Privada").

## Colocando na internet (acessar de qualquer lugar, fora de casa)

Hoje o app guarda tudo num arquivo local (SQLite) — funciona perfeitamente na rede de casa. Para acessar de qualquer lugar, o app precisa ficar hospedado em algum serviço, ligado o tempo todo. Um ponto importante: **Vercel não é indicado aqui** — ele roda em modelo "serverless" (o sistema de arquivos é apagado a cada reinício da função), então um banco de dados local se perderia a cada redeploy. Para um app com login, banco de dados e upload de arquivos, o caminho certo é um serviço que mantém um servidor "vivo" com disco persistente. Do mais simples ao mais robusto:

1. **PythonAnywhere** — o mais simples para quem nunca fez deploy, ótimo para Flask + SQLite, tem plano gratuito limitado.
2. **Railway.app** — conecta direto num repositório Git, tem volume persistente para o banco e os arquivos (fotos/comprovantes), plano de entrada barato.
3. **Fly.io** — parecido ao Railway, com camada gratuita generosa e volumes persistentes.

Qualquer uma dessas eu ajudo a configurar quando vocês decidirem qual seguir. Antes de expor na internet: troquem as senhas padrão por senhas fortes, e — se o serviço oferecer — ativem HTTPS (a maioria já vem com isso de graça). O limitador de tentativas de login já protege contra tentativas repetidas de adivinhar a senha.

## Onde ficam os dados

Tudo fica salvo localmente: lançamentos no arquivo `financas.db` (SQLite), comprovantes na pasta `comprovantes/`, fotos do mural de sonhos na pasta `sonhos/` — todos dentro desta mesma pasta do app, nada vai para a internet a menos que vocês decidam hospedar em algum serviço. Vale a pena, de vez em quando, usar o botão de backup na tela de Perfil (ou copiar essas pastas/arquivo manualmente) para um lugar seguro.

## Próximos passos possíveis (se quiser evoluir depois)

- Editar lançamentos já salvos (hoje só dá pra excluir e recriar)
- Exportar relatório em PDF/Excel
- Cálculo automático de rendimento dos investimentos com base nas taxas do Banco Central
- Migração do banco para PostgreSQL, caso decidam hospedar na nuvem com múltiplos acessos simultâneos
