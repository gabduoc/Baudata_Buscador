import streamlit as st
from flask import Flask, request, jsonify
import time
import requests
import threading
import subprocess
import json
import os
import re

TEMP_FILE = "ultimo_contacto.json"

#Ejecutar programa con:  python -m streamlit run app.py

st.set_page_config(page_title="Baudata CSV Generator", page_icon="🏠", layout="wide")

st.title("🏠 Baudata CSV Generator ")
st.markdown("---")

# --- Barra Lateral para Configuración Global ---
st.sidebar.image("https://baudata.app/assets/assets/images/logo_baudata3_nuevo.80112c02e6d937888ba9ff2325429a97.png", use_container_width=True)
st.sidebar.markdown("---") 
st.sidebar.header("⚙️ Configuración")
api_key = st.sidebar.text_input("Apollo API Key", type="password", help="Obtenla en developer.apollo.io").strip().replace(" ","")
webhook_url = st.sidebar.text_input("Ngrok Webhook URL", placeholder="https://...ngrok-free.dev").strip().replace(" ","")

st.sidebar.markdown(
    "<div style='text-align: center; color: gray; margin-top: 20px;'>"
    "<small>🎩 Desarrollado por <b>Gabriel Zepeda</b> | 2026</small>"
    "</div>", 
    unsafe_allow_html=True
)



# --- Pestañas principales ---
tab_buscar, tab_generar, tab_status = st.tabs([
    "🔍 Buscador de Empresas", 
    "📄 Generador de CSV", 
    "📊 Estado del Servidor"
])

# --- PESTAÑA 1: BUSCADOR DE EMPRESAS ---
with tab_buscar:
    st.subheader("🔍 Buscador de Entidades en Apollo")
    st.markdown("Utiliza cualquiera de las dos opciones para obtener el **ID de la Empresa**, necesario para el generador de CSV.")

    # Definimos los headers comunes para la API (usando la API Key de la barra lateral)
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "X-Api-Key": api_key if api_key else ""
    }

    # Creamos dos columnas visuales separadas para organizar las opciones
    col1, col2 = st.columns(2)
    
    # --- OPCIÓN 1: BUSCAR POR NOMBRE ---
    with col1:
        st.write("### 🏢 Opción 1: Buscar por Nombre")
        nombre_empresa = st.text_input("Nombre de la empresa a buscar ID:", key="input_nombre")
        
        if st.button("Buscar por Nombre", use_container_width=True):
            if not api_key:
                st.error("⚠️ Por favor, ingresa tu Apollo API Key en la barra lateral.")
            elif not nombre_empresa:
                st.warning("⚠️ Escribe un nombre antes de buscar.")
            else:
                with st.spinner(f"Buscando '{nombre_empresa}'..."):
                    url = "https://api.apollo.io/api/v1/organizations/search"
                    data = {"q_organization_name": nombre_empresa}
                    
                    try:
                        res = requests.post(url, headers=headers, json=data)
                        if res.status_code == 200:
                            data_json = res.json()
                            # Intentamos obtener los resultados buscando bajo ambas llaves por seguridad
                            resultados = data_json.get('organizations') or data_json.get('accounts') or []
                            
                            if not resultados:
                                st.info(f"❌ No se encontraron resultados para '{nombre_empresa}'.")
                            else:
                                # Convertimos los resultados a una lista limpia para mostrarla en tabla
                                lista_tabla = []
                                for org in resultados:
                                    lista_tabla.append({
                                        "ID (Copiar este)": org.get('id'),
                                        "Nombre": org.get('name'),
                                        "Sitio Web": org.get('primary_domain', 'N/A')
                                    })
                                
                                st.success(f"🎉 Se encontraron {len(resultados)} resultados:")
                                # Muestra los datos en una tabla interactiva donde se puede copiar el ID haciendo doble clic
                                st.dataframe(lista_tabla, use_container_width=True)
                        else:
                            st.error(f"Error {res.status_code}: {res.text}")
                    except Exception as e:
                        st.error(f"Ocurrió un error en la conexión: {e}")
    
    # --- OPCIÓN 2: BUSCAR POR SITIO WEB ---
    with col2:
        st.write("### 🌐 Opción 2: Buscar por Sitio Web")
        sitio_web = st.text_input("Ingrese sitio web de la página que busca:", placeholder="ej: galilea.cl", key="input_web")
        
        if st.button("Buscar por Dominio", use_container_width=True):
            if not api_key:
                st.error("⚠️ Por favor, ingresa tu Apollo API Key en la barra lateral.")
            elif not sitio_web:
                st.warning("⚠️ Ingrese un dominio válido.")
            else:
                # Limpieza automática del 'www.' tal cual estaba en tu código original [cite: 14]
                pagina_limpia = sitio_web.replace("www.", "")
                
                with st.spinner(f"Buscando dominio '{pagina_limpia}'..."):
                    url = "https://api.apollo.io/api/v1/mixed_companies/search"
                    data = {"q_organization_domains_list": [pagina_limpia]}
                    
                    try:
                        res = requests.post(url, headers=headers, json=data)
                        if res.status_code == 200:
                            data_json = res.json()
                            # Validamos ambas llaves de respuesta tal como aprendimos antes
                            resultados = data_json.get('accounts') or data_json.get('organizations') or []
                            
                            if not resultados:
                                st.info(f"❌ No se encontraron resultados para '{pagina_limpia}'.")
                            else:
                                lista_tabla = []
                                for org in resultados:
                                    lista_tabla.append({
                                        "ID (Copiar este)": org.get('id'),
                                        "Nombre": org.get('name'),
                                        "Sitio Web": org.get('primary_domain', 'N/A')
                                    })
                                
                                st.success(f"🎯 Empresa localizada exitosamente:")
                                st.dataframe(lista_tabla, use_container_width=True)
                        else:
                            st.error(f"Error {res.status_code}: {res.text}")
                    except Exception as e:
                        st.error(f"Ocurrió un error en la conexión: {e}")

# --- PESTAÑA 2: GENERADOR DE CSV ---
with tab_generar:
    st.subheader("📄 Extracción y Enriquecimiento de Trabajadores")
    st.markdown("Esta sección ejecutará el algoritmo de enriquecimiento por *waterfall* respetando los tiempos de espera del webhook.")

    # 1. Inputs del usuario ordenados horizontalmente (reemplazan a los inputs de consola)
    col_in1, col_in2, col_in3 = st.columns([2, 2, 1])
    
    with col_in1:
        id_empresa_input = st.text_input("ID de la Empresa (Account ID):", key="gen_id_empresa").strip().replace(" ", "")
    with col_in2:
        nombre_csv_input = st.text_input("Nombre para el archivo CSV (sin '.csv'):", placeholder="Ej: Reporte_Galilea", key="gen_nombre_csv").strip()
    with col_in3:
        # NUEVO: Input numérico dinámico para el tiempo de espera (Mínimo 1s, Máximo 300s, por defecto 40s)
        max_wait_input = st.number_input(
            "Espera Máx (seg):", 
            min_value=1, 
            max_value=300, 
            value=40, 
            step=1,
            help="Tiempo máximo en segundos que el sistema esperará por el webhook de cada persona.",
            key="gen_max_wait"
        )

    # Botón para iniciar el proceso
    if st.button("🚀 Iniciar Enriquecimiento e Inyección de Webhook", use_container_width=True):
        if not api_key:
            st.error("⚠️ Por favor, ingresa tu Apollo API Key en la barra lateral.")
        elif not webhook_url:
            st.error("⚠️ Es obligatorio configurar la URL de Ngrok en la barra lateral para recibir los webhooks.")
        elif not id_empresa_input or not nombre_csv_input:
            st.warning("⚠️ Debes rellenar el ID de la empresa y el nombre del archivo de salida.")
        else:
            # 2. Re-armar las variables exactas que usa tu lógica
            headers = {'Content-Type': 'application/json', 'X-Api-Key': api_key}
            webhook_completo = webhook_url.rstrip("/") + "/webhook-apollo"
            
            output_dir = "csv"
            os.makedirs(output_dir, exist_ok=True)
            nombre_archivo = os.path.join(output_dir, nombre_csv_input + ".csv")

            st.info("🔄 Conectando con la API de Apollo...")
            
            # 3. Caja de consola virtual para volcar los logs idénticos a tu script original
            log_box = st.empty()
            log_texto = "=== INICIANDO EXPORTACIÓN CON REFINAMIENTO ===\n"
            log_box.code(log_texto)

            # --- INICIO DE TU LÓGICA ESTRICTA (COPIADA TAL CUAL) ---
            try:
                # Búsqueda de empleados (No consume créditos)
                res_search = requests.post(
                    "https://api.apollo.io/api/v1/mixed_people/api_search", 
                    headers=headers, 
                    json={"organization_ids": [id_empresa_input]}
                )
                personas = res_search.json().get('people', [])
                datos_finales = []

                if not personas:
                    log_texto += f"❌ No se encontraron personas vinculadas al ID: {id_empresa_input}\n"
                    log_box.code(log_texto)
                else:
                    log_texto += f"💡 Empleados encontrados: {len(personas)}. Iniciando ciclo de match...\n"
                    log_box.code(log_texto)

                    for p in personas:
                        p_id = str(p.get('id', ''))
                        nombre_trabajador_log = p.get('first_name', 'Empleado')
                        log_texto += f"\n>>> Procesando: {nombre_trabajador_log} (ID: {p_id})...\n"
                        log_box.code(log_texto)

                        # ENRIQUECIMIENTO: enviamos el webhook y pedimos waterfall de email/teléfono
                        match_url = "https://api.apollo.io/api/v1/people/match"
                        params = {
                            "id": p_id,
                            "run_waterfall_email": "true",
                            "run_waterfall_phone": "true",
                            "reveal_personal_emails": "true",
                            "reveal_phone_number": "true"
                        }
                        payload = {
                            "id": p_id,
                            "reveal": True,
                            "webhook_url": webhook_completo, # Usamos la URL dinámica de tu barra lateral
                            "run_waterfall_email": True,
                            "run_waterfall_phone": True,
                            "reveal_personal_emails": True,
                            "reveal_phone_number": True
                        }

                        res_match = requests.post(match_url, headers=headers, params=params, json=payload)

                        if res_match.status_code != 200:
                            log_texto += f"⚠️ Advertencia: la petición de match devolvió {res_match.status_code}\n"
                            log_box.code(log_texto)

                        nombre_trabajador, nombre_empresa, linkedin = "N/A", "N/A", "N/A"
                        direct_email = "N/A"
                        
                        if res_match.status_code == 200:
                            data_p = res_match.json().get("person", {})
                            nombre_trabajador = data_p.get("name", "N/A")
                            linkedin = data_p.get("linkedin_url", "N/A")
                            nombre_empresa = data_p.get("organization", {}).get("name", "N/A")

                            direct_email = data_p.get("email") or "N/A"
                            if direct_email == "N/A":
                                emails = data_p.get("emails", [])
                                if isinstance(emails, list) and emails:
                                    first_email = emails[0]
                                    if isinstance(first_email, dict):
                                        direct_email = first_email.get("email", direct_email)
                                    elif isinstance(first_email, str):
                                        direct_email = first_email

                            # ESPERA DEL WEBHOOK - MODIFICADO CON TU VARIABLE DINÁMICA
                            email, tel = direct_email, "N/A"
                            max_wait = int(max_wait_input) # <--- Aquí el bucle adopta el valor de la interfaz
                            log_texto += f"⏳ Esperando webhook para ID {p_id} (Máx {max_wait}s)...\n"
                            log_box.code(log_texto)
                            
                            for second in range(max_wait):
                                time.sleep(1)
                                if os.path.exists(TEMP_FILE):
                                    with open(TEMP_FILE, 'r', encoding='utf-8') as f:
                                        try:
                                            temp = json.load(f)
                                        except json.JSONDecodeError:
                                            temp = {}
                                        if p_id in temp:
                                            email = temp[p_id].get("email", email)
                                            tel = temp[p_id].get("telefono", "N/A")
                                            log_texto += f"✅ Webhook recibido! email={email}, tel={tel}\n"
                                            log_box.code(log_texto)
                                            break
                                if second % 5 == 4:
                                    log_texto += f"  - esperando webhook... {second + 1}s\n"
                                    log_box.code(log_texto)
                            
                            if email is None: email = "N/A"
                            if tel is None: tel = "N/A"
                            
                            # Agregar fila (7 columnas) SOLO si no ambos son N/A
                            if not (email == "N/A" and tel == "N/A"):
                                datos_finales.append([id_empresa_input, nombre_empresa, nombre_trabajador, p.get('title', 'N/A'), email, tel, linkedin])

                    # ESCRIBIR CSV FINAL
                    import csv
                    with open(nombre_archivo, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(["Id empresa", "Nombre de empresa", "Nombre del trabajador", 
                                         "Puesto del trabajador", "Correo del trabajador", "Teléfono del trabajdor", "LinkedIn del trabajador"])
                        writer.writerows(datos_finales)
                    
                    log_texto += f"\n🏆 PROCESO TERMINADO. Archivo '{nombre_archivo}' generado con éxito.\n"
                    log_box.code(log_texto)
                    st.success(f"🎉 ¡Hecho! El archivo CSV fue guardado en: `{nombre_archivo}`")
                    
                    # BONUS: Permitir al usuario descargar el archivo directamente desde el navegador
                    with open(nombre_archivo, 'rb') as file_download:
                        st.download_button(
                            label="📥 Descargar archivo CSV generado",
                            data=file_download,
                            file_name=os.path.basename(nombre_archivo),
                            mime="text/csv"
                        )

            except Exception as e:
                st.error(f"Ocurrió un error crítico durante la ejecución: {e}")

# --- PESTAÑA 3: ESTADO ---
with tab_status:
    st.subheader("🛰️ Monitoreo del Servidor")
    
    if st.session_state.get('server_started'):
        st.success("Servidor Interno: ACTIVO (Puerto 5000)")
    else:
        st.error("Servidor Interno: APAGADO")

    st.info("Recuerda que debes tener ngrok apuntando al puerto 5000\nPuedes activar ngrok con el siguiente comando en tu terminal:\n\n```\nngrok http 5000\n```\n\nLuego copia la URL que te proporciona ngrok en la barra lateral de configuración.\n\n[Guía Rápida de Ngrok](https://ngrok.com/docs)")
    
    # Mostrar los últimos contactos capturados en tiempo real
    if os.path.exists(TEMP_FILE):
        st.write("Últimos datos capturados:")
        with open(TEMP_FILE, 'r') as f:
            data = json.load(f)
            st.json(data) # Esto muestra el JSON de forma bonita en la app

#========================== CONFIGURACION DEL SEERVIDOR ==============================
# --- CONFIGURACIÓN DE LOGICA (Proveniente de servidor2.py) ---
app = Flask(__name__)
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def find_email(obj):
    # Reutilizamos tu función original para no perder precisión 
    if isinstance(obj, str):
        match = EMAIL_REGEX.search(obj)
        return match.group(0) if match else None
    if isinstance(obj, dict):
        if "email" in obj and obj["email"]: return obj["email"]
        for value in obj.values():
            res = find_email(value)
            if res: return res
    return None

def find_first_value(obj, keys):
    # Reutilizamos tu lógica de búsqueda de teléfonos 
    if isinstance(obj, dict):
        for key in keys:
            if obj.get(key): return obj.get(key)
        for value in obj.values():
            res = find_first_value(value, keys)
            if res: return res
    return None

# --- RUTA DEL WEBHOOK ---
@app.route('/webhook-apollo', methods=['POST'])
def apollo_webhook():
    data = request.json
    if not data:
        return jsonify({"status": "error"}), 400
    
    # Lógica de extracción simplificada para la integración
    # Aquí puedes añadir todas tus funciones 'extract_person_records' si lo deseas
    try:
        # Ejemplo rápido basado en tu servidor original 
        p_id = str(data.get("id", "desconocido")) 
        correo = find_email(data) or "N/A"
        telefono = find_first_value(data, ["sanitized_number", "phone"]) or "N/A"

        # Guardar en el temporal que usa tu generador_csv.py 
        temp_data = {}
        if os.path.exists(TEMP_FILE):
            with open(TEMP_FILE, 'r') as f: temp_data = json.load(f)
        
        temp_data[p_id] = {"email": correo, "telefono": telefono}
        with open(TEMP_FILE, 'w') as f: json.dump(temp_data, f, indent=4)
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- FUNCIÓN PARA INICIAR EL SERVIDOR ---
def run_flask():
    # El puerto 5000 debe estar libre para ngrok [cite: 1]
    app.run(port=5000, debug=False, use_reloader=False)

# Iniciar el servidor en un hilo si no está corriendo
if 'server_started' not in st.session_state:
    thread = threading.Thread(target=run_flask, daemon=True)
    thread.start()
    st.session_state['server_started'] = True

