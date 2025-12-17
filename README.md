# KPI Manager

Esta aplicación web implementa un sistema de administración de KPIs por puesto y un
administrador de organigrama con autenticación, catálogos de puestos y KPIs,
gestión de personal y visualización del organigrama.  Fue desarrollada desde
cero para cumplir con los requisitos descritos en el enunciado.  Utiliza
**Flask** como framework web y **MySQL** como base de datos.

## Requisitos previos

- **Python 3.8–3.14** con `pip`.  Este proyecto es compatible con
  versiones modernas de Python, incluida la versión 3.14.  Debido a que
  Python 3.14 eliminó algunas funciones internas que versiones
  anteriores de Flask utilizaban, la aplicación incluye un pequeño
  *shim* para restablecer `pkgutil.get_loader`.  Adicionalmente, el
  archivo `requirements.txt` ha sido actualizado para requerir
  **Flask 3.0** o superior.  Si utiliza Python 3.14, asegúrese de
  instalar una versión reciente de Flask ejecutando `pip install -r
  requirements.txt` después de crear el entorno virtual.

- MySQL 8 o superior instalado en el mismo equipo o accesible a través de
  `localhost`.  Se asumió en el enunciado que el usuario de MySQL es
  `root` con contraseña `B1Admin`.

## Instalación y configuración

1. Cree la base de datos y las tablas ejecutando el script
   `kpi_manager_schema.sql` en su servidor MySQL.  Puede hacerlo desde la
   línea de comandos así:

   ```sh
   mysql -u root -p < kpi_manager_schema.sql
   ```

   Esto eliminará cualquier base de datos llamada `kpi_manager` y la volverá
   a crear con la estructura necesaria.  El script también inserta todos
   los departamentos y puestos descritos en el archivo de Excel que se
   proporcionó.

2. (Opcional) Cree usuarios del sistema insertando registros en la tabla
   `usuarios`.  Cada usuario debe tener un `empleado_id` válido (es decir,
   un registro en la tabla `empleados`) y un nombre de usuario y contraseña.
   Los roles válidos son `admin`, `jefe` y `empleado`.  **Las
   contraseñas se almacenan en texto plano porque así lo solicitó el
   usuario; no es una práctica recomendable para producción**.  Ejemplo:

   ```sql
   USE kpi_manager;
   INSERT INTO empleados (id_empleado, nombre) VALUES ('0001','Administrador');
   INSERT INTO usuarios (empleado_id, username, password, rol) VALUES (LAST_INSERT_ID(), 'admin', 'admin', 'admin');
   ```

3. Instale las dependencias de Python con `pip`:

   ```sh
   cd kpi_manager_app
   # Cree un entorno virtual.  Con Python 3.14 puede usar el comando `py` en Windows:
   python -m venv venv    # o bien `py -m venv venv` si su alias `python` no está configurado
   
   # Active el entorno virtual (Linux/macOS)
   source venv/bin/activate
   # En Windows PowerShell use:
   # .\venv\Scripts\Activate.ps1
   
   # Instale las dependencias.  Esto instalará Flask 3 y PyMySQL.  Si
   # utiliza Python 3.14, el *shim* en `app.py` permitirá que Flask 2.x
   # continúe funcionando, pero se recomienda utilizar Flask 3.x o superior.
   pip install -r requirements.txt
   ```

4. Ejecute la aplicación:

   ```sh
   flask --app app run
   ```

   La aplicación estará disponible en `http://localhost:5000/`.  Inicie
   sesión con el usuario creado en el paso 2.

## Funcionalidades principales

- **Inicio de sesión:** pantalla de login que redirige a “Mis KPIs” al
  autenticarse correctamente.  Las credenciales se verifican contra la
  tabla `usuarios`.
- **Mis KPIs:** muestra los KPIs asignados al puesto del usuario para el
  periodo en curso (mes actual).  Permite capturar valores numéricos o
  texto (si el KPI es de criterio) y ver el color del semáforo según los
  rangos.  También permite consultar y capturar los KPIs de los
  subordinados directos y cerrar el periodo.
- **Catálogo de KPIs:** buscador por descripción, ID o departamento.
  Contiene un generador para crear nuevos KPIs y permite editarlos en un
  modal.  Soporta KPIs numéricos (con objetivos y rangos) o de criterio
  (solo texto).
- **Puestos:** lista de los puestos existentes, su departamento y su jefe
  inmediato.  Permite editar la información del puesto, crear nuevos
  puestos y asignar KPIs a cada puesto mediante una interfaz de
  selección múltiple.
- **Personal:** buscador y listado de todos los empleados.  Permite
  editar el nombre, puesto, jefe directo y correo electrónico de cada
  empleado.  Incluye un botón **Actualizar personal** que importa
  automáticamente nuevos registros de la tabla `incidencias`, creando
  empleados que no existan aún.
- **Organigrama:** representa gráficamente la estructura jerárquica
  utilizando **jsTree**.  Muestra los puestos como nodos del árbol y,
  debajo de cada puesto, a los empleados asignados.  Se pueden arrastrar
  los nombres de los empleados a otro puesto y, previa confirmación,
  su asignación se actualiza en la base de datos.

## Notas importantes

- El diseño utiliza colores claros y una interfaz moderna basada en
  Bootstrap 5.  Se incluyen alertas de Bootstrap para mostrar
  mensajes de confirmación y error.
- La autenticación no utiliza cifrado ni hashing de contraseñas; las
  credenciales viajan en texto plano.  Esto solo se implementó así
  porque fue requisito explícito.  **Nunca utilice este enfoque en un
  entorno de producción real.**
- El organigrama utiliza jsTree para simplificar la representación y
  permitir la reasignación de empleados con arrastrar y soltar.  Para
  situaciones más complejas podrían emplearse otras bibliotecas como
  d3.js o GoJS.

## Estructura de directorios

```
kpi_manager_schema.sql      Script de creación de base de datos y carga de puestos
kpi_manager_app/
├── app.py                 Código principal de la aplicación Flask
├── requirements.txt       Dependencias de Python
├── static/                Recursos estáticos (CSS, JS)
│   └── css/style.css      Estilos personalizados
├── templates/             Plantillas HTML de Jinja2
│   ├── layout.html        Plantilla base con navegación
│   ├── login.html         Formulario de inicio de sesión
│   ├── mis_kpis.html      Vista de captura de KPIs
│   ├── mis_kpis_no_puesto.html Mensaje cuando no hay puesto asignado
│   ├── kpis.html          Catálogo y editor de KPIs
│   ├── puestos.html       Administración de puestos
│   ├── personal.html      Administración de personal
│   └── organigrama.html   Visualización del organigrama
└── README.md              Este documento
```

Disfrute utilizando el sistema y adáptelo según sus necesidades.

## Railway (deploy)

1) Asegúrate de que el servicio use el comando de arranque:

```
gunicorn app:app --bind 0.0.0.0:$PORT
```

(El repo incluye `Procfile` con ese comando).

2) En Railway **no subas el archivo `.env`**. Configura variables en la pestaña *Variables*:

- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- (Opcional) `INCIDENCIAS_DB_HOST`, `INCIDENCIAS_DB_PORT`, `INCIDENCIAS_DB_USER`, `INCIDENCIAS_DB_PASSWORD`, `INCIDENCIAS_DB_NAME`

Si la DB de incidencias no está configurada, el botón de importar solo mostrará un aviso.

## Local (Windows / VSCode)

1) Crea y activa un entorno:

```
python -m venv venv
venv\Scripts\activate
```

2) Instala dependencias:

```
pip install -r requirements.txt
```

3) Crea un archivo `.env` con tu conexión local (ejemplo):

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=...
DB_NAME=kpi_manager
```

4) Ejecuta:

```
python app.py
```

La pantalla **Personal** está paginada (100 por página) y el buscador busca en toda la tabla.
