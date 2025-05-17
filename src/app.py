import pandas as pd
import json
import unicodedata
from dash import Dash, html, dcc, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import os
 
# -------- Configuración de estilo Plotly --------
px.defaults.template = "plotly_dark"
 
# -------- Función de normalización --------
def normalizar(texto):
    if pd.isnull(texto):
        return ""
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8')
    return texto.upper().strip()
 
# -------- Carga y preprocesamiento --------
#df = pd.read_parquet("mortalidad_2019_limpio.parquet.gzip")
# Ruta segura y relativa dentro de src/
current_dir = os.path.dirname(__file__)
parquet_path = os.path.join(current_dir, "mortalidad_2019_limpio.parquet.gzip")
df = pd.read_parquet(parquet_path)
for col in ['DEPARTAMENTO', 'MUNICIPIO']:
    df[col] = df[col].apply(normalizar)


geo_path = os.path.join(current_dir, "Colombia.geo.json")
with open(geo_path, encoding="utf-8") as f:
    geojson = json.load(f)
for feat in geojson['features']:
    feat['id'] = normalizar(feat['properties']['NOMBRE_DPT'])
 
correcciones = {
    "ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA Y SANTA CATALINA": "SAN ANDRES",
    "BARRANQUILLA D.E.": "ATLANTICO",
    "BOGOTA, D.C.": "SANTAFE DE BOGOTA D.C",
    "BUENAVENTURA D.E.": "VALLE DEL CAUCA",
    "CARTAGENA D.T. Y C.": "BOLIVAR",
    "SANTA MARTA D.T. Y C.": "MAGDALENA"
}
df['DEPARTAMENTO'] = df['DEPARTAMENTO'].replace(correcciones)
for feat in geojson['features']:
    feat['id'] = correcciones.get(feat['id'], feat['id'])
 
# Agregados principales
depart_counts = df.groupby('DEPARTAMENTO').size().reset_index(name='Muertes')
depart_counts['Porcentaje'] = depart_counts['Muertes'] / depart_counts['Muertes'].sum() * 100
mes_counts = df.groupby('MES').size().reset_index(name='Muertes')
df_hom = df[df['COD_MUERTE'].astype(str).str.startswith(tuple(['X95','X96','X97','X98','X99','Y00','Y01','Y02','Y03']))]
top_5_violentas = df_hom.groupby('MUNICIPIO').size().reset_index(name='Homicidios').nlargest(5, 'Homicidios')
df_edad = df.groupby('GRUPO_EDAD1').size().reset_index(name='Total')
df_edad.rename(columns={'GRUPO_EDAD1': 'GrupoEdad'}, inplace=True)
 
# -------- Creación de la app --------
app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])

server = app.server
 
app.layout = dbc.Container(
    fluid=True,
    style={"backgroundColor": "#2b2b3c", "color": "#fff"},
    children=[
        # Navbar superior
        dbc.NavbarSimple(
            brand="📊 Mortalidad Colombia 2019",
            color="dark", dark=True, sticky="top", style={"marginLeft": "-370px"}
        ),
        # Layout principal
        dbc.Row([
            # Sidebar de filtros
            dbc.Col(
                width=3,
                className="pe-0",
                children=[
                    dbc.Card(
                        [
                            dbc.CardHeader("Filtros", className="bg-secondary text-white"),
                            dbc.CardBody(
                                [
                                    html.Label("Departamento", style={"color": "#fff"}),
                                    dcc.Dropdown(
                                        id="filter-dep",
                                        options=[{"label": d, "value": d} for d in sorted(df['DEPARTAMENTO'].unique())],
                                        placeholder="Todos",
                                        value=None,
                                        clearable=True,
                                        searchable=True,
                                        style={"backgroundColor": "#3a3a4d", "color": "#000"}
                                    ),
                                    html.Br(),
                                    html.Label("Rango de Meses", style={"color": "#fff"}),
                                    dcc.RangeSlider(
                                        id="filter-mes",
                                        min=1, max=12, step=1,
                                        marks={i: str(i) for i in range(1, 13)},
                                        value=[1, 12],
                                        tooltip={"placement": "bottom", "always_visible": False}
                                    )
                                ]
                            )
                        ],
                        className="sticky-top mb-3",
                        style={"backgroundColor": "#3a3a4d"}
                    ),
                    dbc.Card(
                        [
                            dbc.CardHeader("Estadísticas", className="bg-secondary text-white"),
                            dbc.CardBody(
                                [
                                    html.P(f"Total muertes: {df.shape[0]:,}", className="fw-bold"),
                                    html.P(f"Departamentos: {df['DEPARTAMENTO'].nunique()}")
                                ]
                            )
                        ],
                        style={"backgroundColor": "#3a3a4d"}
                    )
                ]
            ),
            # Contenido central
            dbc.Col(
                width=9,
                children=[
                    dbc.Tabs(
                        [
                            dbc.Tab(label="Visión General", tab_id="tab-overview"),
                            dbc.Tab(label="Detalle Dep.", tab_id="tab-detail")
                        ],
                        id="tabs", active_tab="tab-overview", className="mt-3"
                    ),
                    html.Div(id="content", className="mt-4")
                ]
            )
        ], className="g-0")
    ]
)
 
# -------- Callbacks --------
@app.callback(
    Output("content", "children"),
    Input("tabs", "active_tab"),
    Input("filter-dep", "value"),
    Input("filter-mes", "value")
)
def render_tab(tab, dep_sel, meses):
    # Filtrar datos
    df_filt = df[(df['MES'] >= meses[0]) & (df['MES'] <= meses[1])]
    filtered_counts = depart_counts if not dep_sel else depart_counts[depart_counts['DEPARTAMENTO'] == dep_sel]
 
    if tab == "tab-overview":
        # Mapa
        fig_map = px.choropleth(
            filtered_counts,
            geojson=geojson,
            locations='DEPARTAMENTO', featureidkey='id',
            color='Muertes', projection='mercator'
        )
        fig_map.update_geos(fitbounds='locations', visible=False)
        fig_map.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=30, b=0))
        # Línea de muertes
        fig_line = px.line(mes_counts, x='MES', y='Muertes', markers=True, title='Muertes por mes')
        fig_line.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        # Top 5 violentas
        fig_viol = px.bar(top_5_violentas, x='MUNICIPIO', y='Homicidios', title='Top 5 Ciudades Violentas')
        fig_viol.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        # Pie ciudades indice de mortalidad
        ##############################
        if(dep_sel == None):
            filtered_counts_mort = df.copy()
        else:
            filtered_counts_mort = df[df["DEPARTAMENTO"] == dep_sel]
 
        filtered_counts_mort_1 = filtered_counts_mort.groupby('MUNICIPIO').size().reset_index(name='Muertes')
        filtered_counts_mort_1['Porcentaje'] = (filtered_counts_mort_1['Muertes'] / filtered_counts_mort_1['Muertes'].sum() * 100)
        df_mortalidad_menores = (
            filtered_counts_mort_1
            .sort_values(by="Porcentaje", ascending=True)
            .head(10)
        )
 
        fig_pie_mort = px.pie(df_mortalidad_menores, names='MUNICIPIO', values='Porcentaje', title=f"10 municipios con menor índice de mortalidad {dep_sel}")
        fig_pie_mort.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        ######################################################################3
        # muertes por sexo por departamento
        muertes_por_sexo_dpto = filtered_counts_mort.groupby(['DEPARTAMENTO', 'SEXO']).size().reset_index(name='TOTAL')
        fig_mort_dept = px.bar(muertes_por_sexo_dpto,
            x="DEPARTAMENTO",
            y="TOTAL",
            color="SEXO",
            barmode="group",
            title="Muertes por sexo en cada departamento"
        )
        fig_mort_dept.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        ############################################
        # Distribución por edad
        fig_edad = px.bar(df_edad.sort_values('GrupoEdad'), x='GrupoEdad', y='Total', title='Distribución por edad')
        fig_edad.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
 
        return html.Div([
            dbc.Row([dbc.Col(dcc.Graph(figure=fig_map), md=6), dbc.Col(dcc.Graph(figure=fig_line), md=6), dbc.Col(dcc.Graph(figure=fig_pie_mort), md=6), dbc.Col(dcc.Graph(figure=fig_mort_dept), md=6)], className="mb-4"),
            dbc.Row([dbc.Col(dcc.Graph(figure=fig_viol), md=6)], className="mb-4")
        ])
    else:

        # dep = dep_sel if dep_sel else depart_counts.loc[depart_counts['Muertes'].idxmax(), 'DEPARTAMENTO']
        if(dep_sel == None):
            dep = "Todos"
            df_dep = df_filt
        else:
            dep = dep_sel if dep_sel else depart_counts.loc[depart_counts['Muertes'].idxmax(), 'DEPARTAMENTO']
            df_dep = df_filt[df_filt['DEPARTAMENTO'] == dep]

        # Detalle gráfico barras
        fig_bar = px.bar(df_dep.groupby('MES').size().reset_index(name='Total'), x='MES', y='Total', title=f'Muertes por mes en {dep}')
        fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        # Pie por sexo
        df_sexo = df_dep['SEXO'].value_counts().reset_index(name='Total')
        df_sexo.columns = ['SEXO', 'Total']
        fig_pie = px.pie(df_sexo, names='SEXO', values='Total', title='Distribución por sexo')
        fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        # Histograma edades detalle
        df_dep["EDAD_INT"] = pd.to_numeric(df_dep["GRUPO_EDAD1"], errors="coerce")
        bins = list(range(0, df_dep["EDAD_INT"].max() + 5, 5))  # Desde 0 hasta la edad máxima
        labels = [f"{i}–{i+4}" for i in bins[:-1]]  # Etiquetas: "0–4", "5–9", etc.
        df_dep["GRUPO_EDAD_5"] = pd.cut(df_dep["EDAD_INT"], bins=bins, labels=labels, right=False)
 
        fig_hist = px.histogram(
            df_dep,
            x="GRUPO_EDAD_5",
            title="Edades agrupadas en intervalos de 5 años",
            category_orders={"GRUPO_EDAD_5": labels}
        )
 
        fig_hist.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        
        # Tabla de causas
        df_dep = df_dep.rename(columns={'Descripcion  de códigos mortalidad a cuatro caracteres': 'Descripcion'})
        causas = df_dep.groupby(['Descripcion',"COD_MUERTE"]).size().nlargest(10).reset_index(name='Total')
        tabla = html.Table([
            html.Thead(html.Tr([html.Th("Descripcion"),html.Th("Codigo"), html.Th("Total")])),
            html.Tbody([html.Tr([html.Td(r.Descripcion), html.Td(r.COD_MUERTE), html.Td(r.Total)]) for r in causas.itertuples()])
        ], className="table table-sm table-dark")
 
        return html.Div([
            html.H4(f"Detalle {dep}", style={"color": "#fff"}),
            dbc.Row([dbc.Col(dcc.Graph(figure=fig_bar), md=6), dbc.Col(dcc.Graph(figure=fig_pie), md=6)], className="mb-4"),
            dbc.Row([dbc.Col(dcc.Graph(figure=fig_hist), md=6), dbc.Col(tabla, md=6)], className="mb-4")
        ], style={"backgroundColor": "#2b2b3c"})
 
if __name__ == "__main__":
    app.run(debug=True, port=8050)
