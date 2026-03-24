import streamlit as st
import pandas as pd
from database import executar_query, ler_dados
import uuid


def render_lancamentos():
    st.header("📝 Gestão de Lançamentos")

    df_contas = ler_dados("cad_contas")
    df_cats = ler_dados("cad_categorias")

    if df_contas.empty or df_cats.empty:
        st.warning("⚠️ O Administrador precisa cadastrar Contas e Hierarquia de Categorias nas Configurações primeiro.")
        return

    pode_editar = st.session_state.get('role') in ["Administrador", "Consegue Ler e Lançamentos"]

    # --- SEÇÃO 1: CADASTRO DE NOVO LANÇAMENTO ---
    if pode_editar:
        with st.expander("➕ Novo Lançamento Detalhado", expanded=True):
            st.markdown("### 1. Tipo de Operação")

            # Adicionado o tipo 'Transferência' para suportar Investimentos/Cofrinho/Apartamento
            tipo = st.radio("Selecione o tipo de movimentação:", ["Gasto", "Ganho", "Transferência"], horizontal=True)

            st.markdown("### 2. Classificação")
            c1, c2, c3 = st.columns(3)

            # Lógica condicional: Transferências não usam a árvore de categorias padrão
            if tipo != "Transferência":
                with c1:
                    grupo_sel = st.selectbox("Grupo", sorted(df_cats['grupo'].unique()))
                with c2:
                    sub_opts = df_cats[df_cats['grupo'] == grupo_sel]['subgrupo'].unique()
                    subgrupo_sel = st.selectbox("Subgrupo", sorted(sub_opts))
                with c3:
                    subcat_opts = df_cats[(df_cats['grupo'] == grupo_sel) &
                                          (df_cats['subgrupo'] == subgrupo_sel)]['subcategoria'].unique()

                    # Verifica se o subgrupo permite split no cadastro
                    permitir_split = False
                    if 'permite_split' in df_cats.columns:
                        permitir_split = df_cats[(df_cats['grupo'] == grupo_sel) &
                                                 (df_cats['subgrupo'] == subgrupo_sel)]['permite_split'].any()

                    usar_split = False
                    if permitir_split:
                        usar_split = st.toggle("🧩 Desmembrar valor por subcategorias?",
                                               help="Ative para distribuir o valor total")
            else:
                st.info("💡 Use 'Transferência' para Cofrinho, Aplicações ou Pagamento de Ativos (Apartamento).")
                usar_split = False

            st.markdown("### 3. Detalhes Financeiros")

            col_v, col_c1, col_c2 = st.columns(3)
            valor_total = col_v.number_input("Valor Total (R$)", min_value=0.0, format="%.2f")
            conta_origem = col_c1.selectbox("Conta (Saída/Origem)", df_contas['nome'].unique(), key="origem")

            # Se for transferência, habilita a conta de destino
            if tipo == "Transferência":
                contas_destino_opts = df_contas[df_contas['nome'] != conta_origem]['nome'].unique()
                conta_destino = col_c2.selectbox("Conta (Destino/Investimento)", contas_destino_opts, key="destino")

            data = st.date_input("Data")
            descricao_geral = st.text_input("Descrição (Ex: Aplicação Cofrinho CDI ou Parcela AP)")

            # --- LÓGICA DE SALVAMENTO ---

            # Caso A: Transferência (Lógica de entrada e saída)
            if tipo == "Transferência":
                if st.button("🚀 Salvar Lançamento", type="primary"):
                    if valor > 0:
                        try:
                            if tipo == "Transferência":
                                # --- LÓGICA DE TRANSFERÊNCIA (SAÍDA E ENTRADA) ---
                                id_agrupador = str(uuid.uuid4())

                                # 1. Saída da conta de origem (Valor Negativo)
                                executar_query("""
                                            INSERT INTO transacoes (valor, tipo, grupo, subgrupo, subcategoria, conta, data, pago, recorrente, descricao, id_agrupador)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        """, (-valor, "Gasto", "Transferência", "Saída", tipo_invest, conta_origem,
                                              data, True, False, f"Saída para {conta_destino}: {descricao}",
                                              id_agrupador))

                                # 2. Entrada na conta de destino (Valor Positivo)
                                executar_query("""
                                            INSERT INTO transacoes (valor, tipo, grupo, subgrupo, subcategoria, conta, data, pago, recorrente, descricao, id_agrupador)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        """, (valor, "Ganho", "Transferência", "Entrada", tipo_invest, conta_destino,
                                              data, True, False, f"Entrada via {conta_origem}: {descricao}",
                                              id_agrupador))

                                st.success(f"✅ Transferência de R$ {valor:,.2f} realizada!")

                            else:
                                # --- LANÇAMENTO NORMAL (GASTO OU GANHO) ---
                                valor_final = -valor if tipo == "Gasto" else valor
                                executar_query("""
                                            INSERT INTO transacoes (valor, tipo, grupo, subgrupo, subcategoria, conta, data, pago, recorrente, descricao)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        """, (valor_final, tipo, grupo_sel, subgrupo_sel, subcat_sel, conta_origem,
                                              data, True, False, descricao))

                                st.success("✅ Lançamento realizado com sucesso!")

                            st.rerun()
                        except NameError as e:
                            st.error(f"Erro de preenchimento: Certifique-se de selecionar Grupo/Subgrupo/Categoria.")
                        except Exception as e:
                            st.error(f"Erro ao salvar: {e}")
                    else:
                        st.error("❌ O valor deve ser maior que zero.")

            # Caso B: Lançamento com Desmembramento (Split)
            elif usar_split:
                st.info("Distribua o valor total abaixo:")
                df_split_data = pd.DataFrame({'Subcategoria': sorted(subcat_opts), 'Valor (R$)': 0.0})
                res_editor = st.data_editor(df_split_data, width='stretch', hide_index=True)

                soma_atual = res_editor['Valor (R$)'].sum()
                diferenca = valor_total - soma_atual
                st.write(f"Soma: **R$ {soma_atual:.2f}** | Restante: **R$ {diferenca:.2f}**")

                if st.button("🚀 Confirmar Lançamento Desmembrado", type="primary"):
                    if abs(diferenca) > 0.01:
                        st.error("A soma das subcategorias não bate com o valor total.")
                    elif valor_total <= 0:
                        st.error("O valor deve ser maior que zero.")
                    else:
                        id_nota = str(uuid.uuid4())[:8]
                        for _, row in res_editor.iterrows():
                            if row['Valor (R$)'] > 0:
                                v_f = -row['Valor (R$)'] if tipo == "Gasto" else row['Valor (R$)']
                                executar_query("""
                                    INSERT INTO transacoes (valor, tipo, grupo, subgrupo, subcategoria, conta, data, pago, recorrente, descricao, id_agrupador)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (v_f, tipo, grupo_sel, subgrupo_sel, row['Subcategoria'], conta_origem, data, True,
                                      False,
                                      f"{descricao_geral} [{row['Subcategoria']}]", id_nota))
                        st.success("Nota desmembrada com sucesso!")
                        st.rerun()

            # Caso C: Lançamento Simples (Gasto ou Ganho)
            else:
                subcat_sel = st.selectbox("Sub-Categoria", sorted(subcat_opts))
                if st.button("💾 Confirmar Lançamento Simples", type="primary"):
                    if valor_total > 0:
                        valor_f = -valor_total if tipo == "Gasto" else valor_total
                        executar_query("""
                            INSERT INTO transacoes (valor, tipo, grupo, subgrupo, subcategoria, conta, data, pago, recorrente, descricao)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (valor_f, tipo, grupo_sel, subgrupo_sel, subcat_sel, conta_origem, data, True, False,
                              descricao_geral))
                        st.success("Lançamento realizado!")
                        st.rerun()
                    else:
                        st.error("O valor deve ser maior que zero.")
        st.divider()
    else:
        st.info("🔒 Seu nível de acesso permite apenas visualização dos lançamentos.")

    # --- SEÇÃO 2: HISTÓRICO E EDIÇÃO ---
    st.subheader("📋 Histórico")
    df_trans = ler_dados("transacoes")

    if not df_trans.empty:
        df_view = df_trans[['id', 'data', 'descricao', 'valor', 'tipo', 'conta', 'grupo', 'subcategoria']].sort_values(
            'data', ascending=False)
        st.dataframe(df_view, width='stretch', hide_index=True)

        if pode_editar:
            with st.expander("✏️ Editar ou 🗑️ Excluir Lançamento Existente"):
                df_trans['label'] = df_trans['id'].astype(str) + " | " + df_trans['data'].astype(str) + " | " + \
                                    df_trans['descricao'] + " | R$ " + df_trans['valor'].astype(str)

                trans_sel_label = st.selectbox("Selecione o Lançamento para Alterar", df_trans['label'].tolist(),
                                               key="sel_trans_edit")

                if trans_sel_label:
                    trans_id = int(trans_sel_label.split(" | ")[0])
                    row = df_trans[df_trans['id'] == trans_id].iloc[0]

                    st.markdown("#### Alterar Dados")

                    grupos = sorted(df_cats['grupo'].unique().tolist() + ["Transferência"])
                    default_g = row['grupo'] if row['grupo'] in grupos else (grupos[0] if grupos else None)
                    edit_g = st.selectbox("Grupo", grupos, index=grupos.index(default_g) if default_g else 0,
                                          key="ed_g")

                    if edit_g == "Transferência":
                        subgrupos = ["Saída", "Entrada"]
                        subcats = ["Investimento", "Transferência"]
                    else:
                        subgrupos = sorted(df_cats[df_cats['grupo'] == edit_g]['subgrupo'].unique())
                        subcats = sorted(
                            df_cats[(df_cats['grupo'] == edit_g) & (df_cats['subgrupo'] == row['subgrupo'])][
                                'subcategoria'].unique())

                    default_sg = row['subgrupo'] if row['subgrupo'] in subgrupos else (
                        subgrupos[0] if subgrupos else None)
                    edit_sg = st.selectbox("Subgrupo", subgrupos,
                                           index=subgrupos.index(default_sg) if default_sg else 0, key="ed_sg")

                    default_sc = row['subcategoria'] if row['subcategoria'] in subcats else (
                        subcats[0] if subcats else None)
                    edit_sc = st.selectbox("Sub-Categoria", subcats,
                                           index=subcats.index(default_sc) if default_sc else 0, key="ed_sc")

                    col_v, col_t, col_c = st.columns(3)
                    val_absoluto = abs(float(row['valor']))
                    edit_val = col_v.number_input("Valor (R$)", min_value=0.0, format="%.2f", value=val_absoluto,
                                                  key="ed_val")
                    edit_tipo = col_t.radio("Tipo", ["Gasto", "Ganho"], horizontal=True,
                                            index=0 if row['tipo'] == "Gasto" else 1, key="ed_tipo")

                    contas_list = df_contas['nome'].unique().tolist()
                    edit_conta = col_c.selectbox("Conta", contas_list, index=contas_list.index(row['conta']) if row[
                                                                                                                    'conta'] in contas_list else 0,
                                                 key="ed_conta")

                    try:
                        data_val = pd.to_datetime(row['data']).date()
                    except:
                        data_val = pd.to_datetime('today').date()

                    col_d, col_desc = st.columns([1, 2])
                    edit_data = col_d.date_input("Data", value=data_val, key="ed_data")
                    edit_desc = col_desc.text_input("Descrição", value=row['descricao'], key="ed_desc")

                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.button("💾 Atualizar Lançamento", type="primary", key="save_edit"):
                        if edit_val > 0:
                            valor_f = -edit_val if edit_tipo == "Gasto" else edit_val
                            executar_query("""
                                UPDATE transacoes
                                SET valor=?, tipo=?, grupo=?, subgrupo=?, subcategoria=?, conta=?, data=?, descricao=?
                                WHERE id=?
                            """, (valor_f, edit_tipo, edit_g, edit_sg, edit_sc, edit_conta, edit_data, edit_desc,
                                  trans_id))
                            st.success("Lançamento atualizado!")
                            st.rerun()
                        else:
                            st.error("O valor deve ser maior que zero.")

                    if col_btn2.button("🗑️ Excluir Lançamento", key="del_trans"):
                        executar_query("DELETE FROM transacoes WHERE id=?", (trans_id,))
                        st.success("Lançamento apagado!")
                        st.rerun()
    else:
        st.info("Nenhum lançamento registrado ainda.")