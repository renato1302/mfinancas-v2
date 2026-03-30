import streamlit as st
import pandas as pd
# Removemos 'executar_query' e 'ler_dados' que eram do DuckDB
# Importamos as funções que conversam com o Supabase
from database import buscar_contas, buscar_categorias, carregar_dados
import uuid
from datetime import datetime


def render_lancamentos():
    st.header("📝 Gestão de Lançamentos")

    # 1. Recupera o usuário logado na sessão (Essencial para o Supabase)
    usuario_atual = st.session_state.get('username')

    # 2. AJUSTE SUPABASE: Buscamos as configurações específicas do usuário
    # Substituímos 'ler_dados' por 'carregar_dados' ou similar filtrando por usuário

    # BUSCA AS CONFIGURAÇÕES (Religando o cabo com as funções novas)
    df_contas = buscar_contas(usuario_atual)
    df_cats = buscar_categorias(usuario_atual)

    # 3. Validação de segurança
    if df_contas.empty or df_cats.empty:
        st.warning("⚠️ O Administrador precisa cadastrar Contas e Hierarquia de Categorias nas Configurações primeiro.")

        # Botão de atalho para facilitar no iPhone
        if st.button("Ir para Configurações"):
            st.session_state.menu_option = "Configurações"
            st.rerun()
        return

    # 4. Controle de Permissões
    pode_editar = st.session_state.get('role') in ["Administrador", "Consegue Ler e Lançamentos"]

    # --- SEÇÃO 1: CADASTRO DE NOVO LANÇAMENTO (OTIMIZADO SUPABASE) ---
    if pode_editar:
        with st.expander("➕ Novo Lançamento", expanded=True):
            st.markdown("### 1. Tipo de Operação")
            # No iPhone, o horizontal=True ajuda a não ocupar muito espaço vertical
            tipo = st.radio("Tipo de movimentação:", ["Gasto", "Ganho", "Transferência"], horizontal=True,
                            key="new_tipo")

            st.markdown("### 2. Classificação e Detalhes")

            # AJUSTE MOBILE: Colunas que se adaptam ao toque
            c1, c2, c3 = st.columns([1, 1, 1])

            usar_split = False

            if tipo != "Transferência":
                with c1:
                    # Pegamos os grupos únicos cadastrados no Supabase para o seu usuário
                    lista_grupos = sorted(df_cats['grupo'].unique())
                    grupo_sel = st.selectbox("Grupo", lista_grupos, key="new_grupo")

                with c2:
                    # Filtra subgrupos baseados no grupo escolhido
                    sub_opts = df_cats[df_cats['grupo'] == grupo_sel]['subgrupo'].unique()
                    sub_opts_sorted = sorted(sub_opts) if len(sub_opts) > 0 else ["Padrão"]
                    subgrupo_sel = st.selectbox("Subgrupo", sub_opts_sorted, key="new_subgrupo")

                with c3:
                    # Filtra subcategorias baseadas no subgrupo
                    filtro_subcat = (df_cats['grupo'] == grupo_sel) & (df_cats['subgrupo'] == subgrupo_sel)
                    subcat_opts = df_cats[filtro_subcat]['subcategoria'].unique()
                    subcat_opts_sorted = sorted(subcat_opts) if len(subcat_opts) > 0 else ["Padrão"]

                    # Lógica de Desmembramento (Split) - Verificação de coluna no Supabase
                    permitir_split = False
                    if 'permite_split' in df_cats.columns:
                        # Verifica se o subgrupo atual permite o desmembramento
                        permitir_split = df_cats[filtro_subcat]['permite_split'].any()

                    if permitir_split:
                        usar_split = st.toggle("🧩 Desmembrar?", help="Ative para distribuir o valor por subcategorias")

                    if not usar_split:
                        subcat_sel = st.selectbox("Subcategoria", subcat_opts_sorted, key="new_subcat")
            else:
                # Padronização para Transferências
                subcat_sel = "Transferência"
                grupo_sel = "Transferência"
                subgrupo_sel = "Transferência"
                st.info("💡 Movimentação entre contas, cofrinho ou aplicações.")

            st.divider()

            # Blocos de Valores e Datas
            d1, d2, d3 = st.columns(3)
            with d1:
                valor_input = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f", key="new_valor")
            with d2:
                # Data padrão hoje (Timezone São Paulo)
                data_lanc = st.date_input("Data", value=datetime.now().date(), key="new_data")
            with d3:
                # Lista de contas vindas do seu cadastro no Supabase
                contas_disponiveis = sorted(df_contas['nome'].unique())
                conta_sel = st.selectbox("Conta Origem", contas_disponiveis, key="new_conta")

            desc = st.text_input("Descrição (Ex: Mercado, Combustível...)", key="new_desc")

            # Campo extra apenas se for transferência
            if tipo == "Transferência":
                conta_dest = st.selectbox("Conta Destino", contas_disponiveis, key="new_conta_dest")

            # --- PROCESSAMENTO DO BOTÃO SALVAR (VERSÃO SUPABASE) ---

            # Caso A: Desmembramento (Split)
            if usar_split:
                st.info("Distribua o valor total abaixo:")
                # Criamos o DataFrame para o editor
                df_split_data = pd.DataFrame({'Subcategoria': sorted(subcat_opts), 'Valor (R$)': 0.0})
                res_editor = st.data_editor(df_split_data, use_container_width=True, hide_index=True,
                                            key="editor_split")

                soma_atual = res_editor['Valor (R$)'].sum()
                diferenca = valor_input - soma_atual  # usando a variável do seu st.number_input

                st.write(f"Soma: **R$ {soma_atual:.2f}** | Restante: **R$ {diferenca:.2f}**")

                if st.button("🚀 Confirmar Lançamento Desmembrado", type="primary", use_container_width=True):
                    if abs(diferenca) > 0.01:
                        st.error("A soma das subcategorias não bate com o valor total.")
                    elif valor_input <= 0:
                        st.error("O valor deve ser maior que zero.")
                    else:
                        try:
                            id_agrupador = str(uuid.uuid4())[:8]
                            sucesso_geral = True

                            for _, row in res_editor.iterrows():
                                if row['Valor (R$)'] > 0:
                                    v_f = -row['Valor (R$)'] if tipo == "Gasto" else row['Valor (R$)']

                                    # PREPARAÇÃO PARA SUPABASE
                                    dados_lanc = {
                                        "valor": v_f,
                                        "tipo": tipo,
                                        "grupo": grupo_sel,
                                        "subgrupo": subgrupo_sel,
                                        "subcategoria": row['Subcategoria'],
                                        "conta": conta_sel,
                                        "data": str(data_lanc),  # Supabase prefere string ISO para data
                                        "descricao": f"{desc} [{row['Subcategoria']}]",
                                        "id_agrupador": id_agrupador,
                                        "usuario_id": usuario_atual  # Mudamos para usuario_id conforme a tabela
                                    }
                                    # CHAMA A FUNÇÃO DO DATABASE.PY
                                    if not inserir_transacao(dados_lanc):
                                        sucesso_geral = False

                            if sucesso_geral:
                                st.success("✅ Nota desmembrada com sucesso no Supabase!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar split: {e}")

            # Caso B: Lançamento Simples ou Transferência
            else:
                if st.button("🚀 Confirmar Lançamento", type="primary", use_container_width=True):
                    if valor_input > 0:
                        try:
                            if tipo == "Transferência":
                                id_transf = str(uuid.uuid4())[:8]

                                # 1. Registro de Saída (Conta Origem)
                                dados_saida = {
                                    "valor": -valor_input,
                                    "tipo": "Transferência",
                                    "grupo": "Transferência",
                                    "subgrupo": "Transferência",
                                    "subcategoria": "Saída",
                                    "conta": conta_sel,
                                    "data": str(data_lanc),
                                    "descricao": f"TR (Saída): {desc}",
                                    "id_agrupador": id_transf,
                                    "usuario_id": usuario_atual
                                }

                                # 2. Registro de Entrada (Conta Destino)
                                dados_entrada = {
                                    "valor": valor_input,
                                    "tipo": "Transferência",
                                    "grupo": "Transferência",
                                    "subgrupo": "Transferência",
                                    "subcategoria": "Entrada",
                                    "conta": conta_dest,
                                    "data": str(data_lanc),
                                    "descricao": f"TR (Entrada): {desc}",
                                    "id_agrupador": id_transf,
                                    "usuario_id": usuario_atual
                                }

                                if inserir_transacao(dados_saida) and inserir_transacao(dados_entrada):
                                    st.success("✅ Transferência realizada com sucesso!")
                                    st.rerun()

                            else:
                                # Lançamento Simples (Gasto ou Ganho)
                                valor_final = -valor_input if tipo == "Gasto" else valor_input

                                dados_simples = {
                                    "valor": valor_final,
                                    "tipo": tipo,
                                    "grupo": grupo_sel,
                                    "subgrupo": subgrupo_sel,
                                    "subcategoria": subcat_sel,
                                    "conta": conta_sel,
                                    "data": str(data_lanc),
                                    "descricao": desc,
                                    "usuario_id": usuario_atual
                                }

                                if inserir_transacao(dados_simples):
                                    st.success("✅ Lançamento registrado no Supabase!")
                                    st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar no Supabase: {e}")
                    else:
                        st.error("O valor deve ser maior que zero.")

    # --- SEÇÃO 2: VISUALIZAÇÃO E EDIÇÃO (FINALIZADO PARA SUPABASE) ---
    st.divider()
    st.subheader("🔍 Lançamentos Recentes")

    # 1. Carregando dados do Supabase filtrados pelo usuário
    # Certifique-se que carregar_dados(usuario_id) está no seu database.py
    df_lista = carregar_dados(usuario_atual)

    if not df_lista.empty:
        # Preparação para exibição no iPhone
        df_display = df_lista.copy()
        df_display['data'] = pd.to_datetime(df_display['data'])

        # Filtro de Mês/Ano para facilitar a navegação mobile
        df_display['mes_ano'] = df_display['data'].dt.strftime('%m/%Y')
        meses_disp = sorted(df_display['mes_ano'].unique(), reverse=True)
        mes_filtro = st.selectbox("📅 Filtrar por Mês/Ano", ["Todos"] + meses_disp, key="filtro_mes_extrato")

        if mes_filtro != "Todos":
            df_display = df_display[df_display['mes_ano'] == mes_filtro]

        # Ordenar pelos mais recentes primeiro
        df_display = df_display.sort_values(by='data', ascending=False)

        # Exibição da Tabela (use_container_width é vital para não cortar no celular)
        colunas_vistas = ['id', 'data', 'tipo', 'grupo', 'subcategoria', 'conta', 'valor', 'descricao']
        st.dataframe(
            df_display[colunas_vistas],
            use_container_width=True,
            hide_index=True,
            column_config={"id": st.column_config.TextColumn("ID")}  # Exibe ID como texto para facilitar cópia
        )

        # --- BLOCO DE EDIÇÃO (Lógica Supabase) ---
        with st.expander("🛠️ Editar ou Excluir Lançamento"):
            st.write("Copie o ID da tabela acima para alterar.")
            # No Supabase o ID pode ser texto (UUID), por isso usamos text_input
            id_para_editar = st.text_input("Cole o ID do lançamento:", key="input_id_edit")

            if id_para_editar:
                # Segurança: Buscamos apenas no que pertence ao usuário logado
                row_sel = df_lista[df_lista['id'].astype(str) == str(id_para_editar)]

                if not row_sel.empty:
                    row = row_sel.iloc[0]
                    st.info(f"📍 Selecionado: {row['descricao']} | R$ {abs(row['valor']):,.2f}")

                    with st.form("form_edicao_supabase"):
                        c_ed1, c_ed2, c_ed3 = st.columns([1, 1, 1])

                        nova_data_ed = c_ed1.date_input("Nova Data", value=pd.to_datetime(row['data']))

                        contas_lista = sorted(list(df_contas['nome'].unique()))
                        idx_conta = contas_lista.index(row['conta']) if row['conta'] in contas_lista else 0
                        nova_conta_ed = c_ed2.selectbox("Nova Conta", contas_lista, index=idx_conta)

                        # Valor sempre positivo no input, o sinal tratamos no salvamento
                        novo_valor_ed = c_ed3.number_input("Novo Valor (R$)", value=abs(float(row['valor'])), step=0.01)

                        nova_desc_ed = st.text_input("Nova Descrição", value=str(row['descricao'] or ""))

                        btn_save, btn_del = st.columns(2)

                        # --- LÓGICA DE SALVAMENTO (UPDATE) ---
                        if btn_save.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True):
                            # Mantém a lógica de sinais (Gasto é negativo, Ganho é positivo)
                            if row['tipo'] == "Transferência":
                                valor_final_ed = -novo_valor_ed if row['valor'] < 0 else novo_valor_ed
                            else:
                                valor_final_ed = -novo_valor_ed if row['tipo'] == "Gasto" else novo_valor_ed

                            # COMANDO SUPABASE: update().eq()
                            from database import supabase
                            res = supabase.table("transacoes").update({
                                "valor": valor_final_ed,
                                "data": str(nova_data_ed),
                                "conta": nova_conta_ed,
                                "descricao": nova_desc_ed
                            }).eq("id", id_para_editar).eq("usuario_id", usuario_atual).execute()

                            if res.data:
                                st.success("✅ Atualizado com sucesso!")
                                st.rerun()

                        # --- LÓGICA DE EXCLUSÃO (DELETE) ---
                        if btn_del.form_submit_button("🗑️ Excluir Registro", use_container_width=True):
                            from database import supabase

                            # Se tiver id_agrupador, exclui o par (Split ou Transferência)
                            if row.get('id_agrupador'):
                                res = supabase.table("transacoes").delete().eq("id_agrupador", row['id_agrupador']).eq(
                                    "usuario_id", usuario_atual).execute()
                                st.warning("⚠️ Grupo de lançamentos removido!")
                            else:
                                res = supabase.table("transacoes").delete().eq("id", id_para_editar).eq("usuario_id",
                                                                                                        usuario_atual).execute()
                                st.warning("⚠️ Lançamento removido!")

                            st.rerun()
                else:
                    st.error("❌ ID não encontrado ou acesso negado.")
    else:
        st.info(f"💡 {usuario_atual}, ainda não há lançamentos. Use o formulário acima para começar!")