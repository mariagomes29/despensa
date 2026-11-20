"""Estética minimalista: fundo branco, tipografia escura, muito espaço, pílulas suaves."""

CSS = """
<style>
:root{
  --texto:#1f2328; --suave:#6b7280; --linha:#f0f1f3; --cinza:#f2f3f5; --cinza2:#e6e8eb;
  --verde-bg:#e7f4ea; --verde:#2f7a45; --laranja-bg:#fdf0e4; --laranja:#a5541c;
}
html, body, .stApp, [class*="css"]{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: var(--texto);
}
.stApp{ background:#ffffff; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"]{ display:none !important; }
header[data-testid="stHeader"]{ background:transparent; height:0; }
.block-container{ max-width: 640px; padding-top: 2.2rem; padding-bottom: 4rem; }
p, li, label, .stMarkdown{ font-size: 1.05rem; }

/* ícones de traço fino */
[data-testid="stIconMaterial"]{ font-variation-settings:'FILL' 0,'wght' 300,'GRAD' 0,'opsz' 24; color:#4b5563; }

/* cabeçalho */
.marca{ font-size:.95rem; font-weight:600; color:var(--suave); letter-spacing:.01em; margin-bottom:1.4rem; }
.saudacao{ font-size:2.1rem; font-weight:700; line-height:1.15; margin:0; }
.subtitulo{ color:var(--suave); font-size:1.05rem; margin:.35rem 0 1.4rem 0; }
.titulo-pag{ font-size:1.7rem; font-weight:700; margin:0 0 .2rem 0; }
.secao{ font-size:.85rem; font-weight:600; color:var(--suave); text-transform:uppercase;
        letter-spacing:.06em; margin:1.6rem 0 .3rem 0; }

/* indicadores grandes */
.cartoes{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:.4rem 0 1.2rem 0; }
.cartao{ border:1px solid var(--linha); border-radius:18px; padding:18px 20px; }
.cartao .num{ font-size:2.8rem; font-weight:700; line-height:1; }
.cartao .rotulo{ color:var(--suave); font-size:.95rem; margin-top:.45rem; }

/* aviso de aprendizagem */
.aprender{ background:#fafafa; border:1px solid var(--linha); border-radius:18px; padding:16px 20px; margin:.2rem 0 .6rem 0; }
.aprender b{ font-weight:600; }
.aprender p{ margin:.25rem 0 0 0; color:var(--suave); font-size:.98rem; }

/* pílulas */
.pilula{ display:inline-block; background:var(--verde-bg); color:var(--verde); border-radius:999px;
         padding:2px 10px; font-size:.8rem; font-weight:600; white-space:nowrap; }
.pilula.aviso{ background:var(--laranja-bg); color:var(--laranja); }
.pilula.neutra{ background:var(--cinza); color:#5b6470; }

/* linhas de lista: não empilhar no telemóvel */
[class*="st-key-linha"] [data-testid="stHorizontalBlock"]{
  flex-wrap:nowrap !important; align-items:center; gap:.6rem;
  border-bottom:1px solid var(--linha); padding:.55rem 0;
}
[class*="st-key-linha"] [data-testid="stColumn"]{ min-width:0 !important; }
[class*="st-key-linha"] [data-testid="stVerticalBlock"]{ gap:.15rem; }
[class*="st-key-linha"] p{ margin:0; }
.nome{ font-size:1.08rem; }
.qtd{ text-align:right; font-weight:700; font-size:1.2rem; }
.cinza{ color:#9aa1ab; font-size:.85rem; margin-left:.25rem; }
.qtd small{ font-weight:400; color:var(--suave); font-size:.85rem; }

/* botões grandes arredondados em cinzento claro */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button{
  border-radius:999px; background:var(--cinza); color:var(--texto); border:none;
  font-weight:600; min-height:3rem; padding:0 1.4rem; box-shadow:none; width:100%;
}
.stButton, .stFormSubmitButton, .stDownloadButton{ width:100%; }
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover{
  background:var(--cinza2); color:#000; border:none;
}
.stButton > button:focus:not(:active){ border:none; box-shadow:none; color:var(--texto); }
.stButton > button:disabled{ background:#f7f7f8; color:#c3c7cd; }

/* botões redondos «+» e «×» nas listas, fáceis de carregar */
[class*="st-key-mais"] button{ width:3.2rem; height:3.2rem; min-height:3.2rem; padding:0;
  border-radius:50%; font-size:1.6rem; line-height:1; }
[class*="st-key-mais"] .stButton{ display:flex; justify-content:flex-end; }

/* campos */
[data-baseweb="input"], [data-baseweb="select"] > div, .stDateInput > div > div{ border-radius:12px !important; }
[data-testid="stExpander"] details{ border:1px solid var(--linha); border-radius:16px; }
[data-testid="stProgress"] > div > div > div > div{ background-color:#8bbf98; }

/* separadores */
[data-baseweb="tab-list"]{ gap:.4rem; }
[data-baseweb="tab"]{ font-size:1rem; }
[data-baseweb="tab-highlight"]{ background-color:#1f2328; }

/* navegação */
[data-testid="stButtonGroup"]{ margin-bottom:1.2rem; }
[data-testid="stButtonGroup"] button{ border-radius:999px !important; min-height:2.6rem; }
</style>
"""
