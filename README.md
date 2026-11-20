# A minha despensa

Aplicação web simples para as compras de casa. Só se registam as **compras** (produto, quantidade
e data). A aplicação aprende **de quanto em quanto tempo** se compra cada produto e prepara a
lista do que comprar esta semana e no próximo mês. Não é preciso contar o que se gasta.

As compras podem ser escritas à mão ou lidas de uma vez a partir de uma **fotografia ou PDF do talão**.

Cada família entra com o **e-mail da casa** (e um código opcional de 4 algarismos). Quem usar o
mesmo e-mail vê e edita a mesma lista; casas diferentes nunca se misturam.

## Ficheiros

| Ficheiro | Para que serve |
|---|---|
| `app.py` | Interface: entrada, Início, A comprar, Produtos, Nova compra |
| `estilo.py` | Estética minimalista (CSS) |
| `acesso.py` | E-mail da casa, código de 4 algarismos e link «lembrar-me» |
| `casa.py` | Produtos e compras (e conversão de ficheiros da versão anterior) |
| `faturas.py` | Leitura de talões (imagem/PDF → Google Gemini) e associação a produtos existentes |
| `previsao.py` | Aprendizagem pela frequência e listas «Em breve» / «Lista do mês» |
| `storage.py` | Um ficheiro JSON por casa (local ou no GitHub privado) |
| `teste_rapido.py` | Testes da lógica, do acesso e da separação entre casas |

## Experimentar no computador

```bash
pip install -r requirements.txt
python teste_rapido.py        # deve terminar com oito linhas "OK" (o Gemini é simulado)
streamlit run app.py
```

Sem configuração, cada casa fica em `dados/casas/<id>.json` (com uma cópia `.json.bak`).

## Como funciona para quem usa

1. **Entrar:** escreve o e-mail da casa e, se quiser, um código de 4 algarismos. Na primeira vez
   a aplicação pergunta se quer criar a casa (assim um e-mail mal escrito não cria uma casa por engano).
2. **Fica lembrada:** depois de entrar, o endereço da página passa a ter `?c=…`. Se guardar a página
   nos favoritos ou no ecrã principal do telemóvel, entra logo sem voltar a escrever o e-mail.
   «Sair desta casa» (em Início → A minha casa) apaga esse lembrete.
3. **Registar compras:**
   - **Ler talão** (em «Nova compra»): tirar ou carregar a fotografia/PDF → «Ler talão» → rever a
     tabela → «Guardar». Ver mais abaixo.
   - **Escrever à mão** (em «Nova compra»): produto, quantidade 1 e data de hoje já preenchidas.
   - Botão **+** na página «Produtos», ou «Comprei» na lista de compras.
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

## Leitura de talões

1. A fotografia é endireitada e reduzida (Pillow). Talões compridos são partidos em até 5 partes
   com sobreposição, para as letras continuarem legíveis. PDFs são enviados tal como estão.
2. A imagem vai para a **API gratuita do Google Gemini** (Google AI Studio), com a lista dos produtos
   que a casa já tem, e volta em JSON estruturado: a loja, a data e, por artigo, o texto do talão, um nome claro
   (ex.: «LEITE MIMOSA M/G 1L» → «Leite meio-gordo Mimosa») e a quantidade («2 X 0,89» = 2;
   artigos a peso = 1). Descontos, totais e IVA são ignorados; sacos vêm sem visto.
3. **Associação aos produtos da casa**, para não criar duplicados:
   1. **memória**: se aquele texto de talão já foi gravado antes, vai para o mesmo produto
      (incluindo as correções feitas na revisão);
   2. a sugestão do modelo, se for exatamente um produto da casa;
   3. semelhança de nomes depois de expandir abreviaturas (M/G, IOG, DET, P.HIG, S/, C/…) e
      ignorar tamanhos (1L, 500G, X6, 40D). Palavras como «sem», «gás» ou «zero» distinguem
      produtos («Manteiga s/sal» não se junta a «Manteiga com sal»);
   4. caso contrário, produto novo.
4. **Revisão:** tabela editável com visto, produto, quantidade e o texto original. Pode corrigir,
   tirar o visto, apagar linhas ou acrescentar na última linha. A data detetada pode ser mudada.
   Nada é gravado antes de carregar em «Guardar».

**Modelos:** por defeito usa o `gemini-3.8-flash`. Se esse modelo não existir para a sua chave,
esgotar a quota gratuita ou estiver sobrecarregado, a app tenta automaticamente o
`gemini-3.5-flash-lite` e depois o `gemini-2.5-flash` (este só funciona em contas que já o usavam).
Pode escolher outro em `modelo`; os nomes disponíveis aparecem no Google AI Studio.

**Custo e limites:** o plano gratuito do Gemini não precisa de cartão de crédito. Tem limites de pedidos
por minuto e por dia, que a Google ajusta e que pode consultar no AI Studio (*Rate limits*). Para os poupar,
há um **limite diário de talões por casa** (`limite_diario`, 20 por defeito). Se a quota acabar, a app
avisa e o registo à mão continua a funcionar.

**Privacidade (importante):** no plano gratuito, a Google pode usar o que é enviado para melhorar os
seus produtos, e pessoas podem rever esse conteúdo. Os talões podem ter o NIF ou parte do número do cartão.
Avise quem usar a app, e prefira talões sem NIF. Se isto for um problema, ative a faturação no
projeto do AI Studio (plano pago), onde os dados não são usados dessa forma. Confirme sempre nos termos
atuais da API do Gemini. As imagens não ficam guardadas na aplicação: só os produtos, quantidades e data.

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

6. **Talões (opcional, gratuito):** entre em [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   com uma conta Google → *Create API key*. Não precisa de cartão. Junte aos Secrets:

   ```toml
   [ia]
   chave_gemini = "AIza..."
   modelo = "gemini-3.8-flash"
   limite_diario = 20
   ```

   Também são aceites os nomes `api_key` ou `gemini_api_key` para a chave. Sem esta secção, o separador
   «Ler talão» explica que a leitura ainda não está ativa e o registo à mão continua a funcionar.
7. **Acesso público:** em *Settings → Sharing*, deixe a app **pública**. O ecrã de entrada por
   e-mail é o que separa as casas.
8. Partilhe o link. Cada família escolhe o seu e-mail (e código). Em Início → *A minha casa* deve aparecer
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
(e-mail, *hash* do código, chave do link), os `produtos`, a lista de `compras`, os `aliases`
(texto de talão → produto, aprendidos na revisão) e o contador de `leituras` por dia. Ficheiros da versão
anterior (com stock) são convertidos automaticamente: as compras mantêm-se e os gastos do botão − são ignorados.
A cópia de segurança descarregada não inclui o bloco `casa`; ao repor, o e-mail e o código mantêm-se.
