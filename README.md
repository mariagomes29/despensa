# A minha despensa

Aplicação web simples para as compras de casa. Só se registam as **compras** (produto, quantidade
e data). A aplicação aprende **de quanto em quanto tempo** se compra cada produto e prepara a
lista do que comprar esta semana e no próximo mês. Não é preciso contar o que se gasta.

Cada família entra com o **e-mail da casa** (e um código opcional de 4 algarismos). Quem usar o
mesmo e-mail vê e edita a mesma lista; casas diferentes nunca se misturam.

## Ficheiros

| Ficheiro | Para que serve |
|---|---|
| `app.py` | Interface: entrada, Início, A comprar, Produtos, Nova compra |
| `estilo.py` | Estética minimalista (CSS) |
| `acesso.py` | E-mail da casa, código de 4 algarismos e link «lembrar-me» |
| `casa.py` | Produtos e compras (e conversão de ficheiros da versão anterior) |
| `previsao.py` | Aprendizagem pela frequência e listas «Em breve» / «Lista do mês» |
| `storage.py` | Um ficheiro JSON por casa (local ou no GitHub privado) |
| `teste_rapido.py` | Testes da lógica, do acesso e da separação entre casas |

## Experimentar no computador

```bash
pip install -r requirements.txt
python teste_rapido.py        # deve terminar com seis linhas "OK"
streamlit run app.py
```

Sem configuração, cada casa fica em `dados/casas/<id>.json` (com uma cópia `.json.bak`).

## Como funciona para quem usa

1. **Entrar:** escreve o e-mail da casa e, se quiser, um código de 4 algarismos. Na primeira vez
   a aplicação pergunta se quer criar a casa (assim um e-mail mal escrito não cria uma casa por engano).
2. **Fica lembrada:** depois de entrar, o endereço da página passa a ter `?c=…`. Se guardar a página
   nos favoritos ou no ecrã principal do telemóvel, entra logo sem voltar a escrever o e-mail.
   «Sair desta casa» (em Início → A minha casa) apaga esse lembrete.
3. **Registar compras:** em «Nova compra» (produto, quantidade 1 e data de hoje já preenchidas),
   no botão **+** da página «Produtos», ou em «Comprei» na lista de compras.
4. **A comprar:** separador «Em breve» (próximos 7 dias) e «Lista do mês» (próximos 30 dias, com a
   quantidade total do mês e uma versão em texto para copiar ou enviar por mensagem).

## Como aprende

- Compras do mesmo produto no mesmo dia contam como uma só.
- **Fase de aprendizagem:** cada produto precisa de 3 compras em dias diferentes (ou 2, se a primeira
  já tiver mais de 30 dias). Até lá aparece «A aprender · 1 de 3 compras».
- **Intervalo habitual:** média ponderada dos últimos 8 intervalos entre compras, em que as compras
  recentes valem mais, depois de cortar valores estranhos (menos de metade ou mais do dobro da mediana,
  por exemplo quando alguém se esquece de registar uma compra).
- **Quantidade habitual:** mediana das últimas 6 compras.
- **Próxima compra** = última compra + intervalo × (quantidade da última ÷ habitual). Se comprar o dobro,
  a próxima compra fica para mais tarde.
- **Lista do mês:** para cada produto, conta quantas vezes se costuma comprar nos próximos 30 dias e
  multiplica pela quantidade habitual.
- Se passar mais de 3× o intervalo habitual sem comprar, o produto deixa de ser sugerido.

Todos estes números estão no topo de `previsao.py` e podem ser ajustados.

## Pôr online (Streamlit Community Cloud, gratuito)

> **Importante:** no Streamlit Cloud o disco é apagado sempre que a app reinicia ou adormece.
> Por isso os dados ficam num **segundo repositório GitHub, privado**, com um ficheiro por casa
> (`casas/<id>.json`). Cada alteração fica no histórico, por isso também é possível recuperar versões antigas.

1. **Repositório do código:** crie um repositório no GitHub (ex.: `despensa`) e envie esta pasta.
2. **Repositório dos dados:** crie outro repositório **privado** (ex.: `despensa-dados`), com um
   README para ter o ramo `main`.
3. **Token:** GitHub → Settings → Developer settings → *Fine-grained tokens* → *Generate new token*.
   - *Repository access*: só `despensa-dados`
   - *Permissions → Contents*: **Read and write**
4. **Publicar:** em [share.streamlit.io](https://share.streamlit.io) → *Create app* → repositório
   `despensa`, ficheiro `app.py`.
5. **Segredos:** na app → *Settings → Secrets*, cole (veja `.streamlit/secrets.toml.exemplo`):

   ```toml
   [github]
   token = "github_pat_..."
   repo = "o-seu-utilizador/despensa-dados"
   pasta = "casas"
   ramo = "main"
   ```

6. **Acesso público:** em *Settings → Sharing*, deixe a app **pública**. O ecrã de entrada por
   e-mail é o que separa as casas.
7. Partilhe o link. Cada família escolhe o seu e-mail (e código). Em Início → *A minha casa* deve aparecer
   «Os dados desta casa estão guardados no GitHub».

## Segurança: o que esperar

Isto é um acesso simples, não um sistema de contas:

- Não se envia nenhum e-mail de confirmação: qualquer pessoa que saiba o e-mail de uma casa **sem
  código** pode entrar nela. Recomende a todos que usem um código.
- O código é guardado só como *hash* (PBKDF2 com sal). Ao fim de 5 tentativas erradas é preciso
  esperar um minuto, mas um código de 4 algarismos protege contra enganos, não contra quem quer adivinhar.
- O link com `?c=…` dá acesso à casa: enviá-lo a alguém é o mesmo que lhe dar a chave.
- Quem administra o repositório `despensa-dados` vê os ficheiros de todas as casas, incluindo os e-mails.
  Não guarde dados sensíveis.

## Formato dos dados

Um ficheiro JSON legível por casa (estrutura descrita no topo de `casa.py`): o bloco `casa`
(e-mail, *hash* do código, chave do link), os `produtos` e a lista de `compras`. Ficheiros da versão
anterior (com stock) são convertidos automaticamente: as compras mantêm-se e os gastos do botão − são ignorados.
A cópia de segurança descarregada não inclui o bloco `casa`; ao repor, o e-mail e o código mantêm-se.
