# 🚇🚆 Transportes de Buenos Aires (`transportes_ba`)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/Lean724/transportes_ba)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Integración personalizada (`custom_component`) para **Home Assistant** que monitorea en tiempo real el estado detallado de la red de **Subte y Premetro (Emova)**, **Trenes Metropolitanos del AMBA (Trenes Argentinos / SOFSE)** y las **próximas salidas desde las estaciones cercanas a tu casa**.

---

## ✨ Características Principales

- **Arquitectura en 2 Capas (Estado de Red + Estaciones Cercanas)**:
  1. **Monitoreo de Líneas**: Elegí todas las líneas de Tren y Subte que forman parte de tu viaje diario sin importar qué tan lejos estén de tu casa.
  2. **Detección Automática de Estaciones por Radio (`km`)**: A partir de la ubicación de tu casa en Home Assistant (`zone.home`) y un radio configurable (por defecto `2.0 km`), pre-selecciona automáticamente las estaciones cercanas de tus líneas habilitadas (y te permite sumar o quitar estaciones manualmente, como la estación de vuelta del trabajo).
- **Estado Directo + Clasificación Inteligente de Alertas**:
  - El estado del sensor muestra **directamente cuál es el problema** (ej. `"Estación Medrano cerrada por obras. Viernes y Sábado con horario extendido."` o `"Servicio limitado entre Once y Castelar"`).
  - Clasifica automáticamente las novedades en `normal`, `aviso` (horarios extendidos o cronogramas futuros), `estacion_cerrada`, `demoras`, `servicio_limitado` e `interrumpido`.
  - Los `binary_sensor` de alerta solo se activan (`on`) ante **problemas operativos reales de circulación** (`demoras`, `servicio_limitado`, `interrumpido`), evitando falsas alarmas por avisos informativos.
- **Próximos Trenes en Tiempo Real (Catálogo de 363 Estaciones Georreferenciadas)**:
  - Consulta cada 60 segundos los próximos arribos en ambos sentidos (`/v1/arribos/estacion/{id}`) para las estaciones de tren seleccionadas, mostrando minutos restantes, andén, ramal y estado de la formación.
  - Detecta si una estación cercana de Subte o Tren se encuentra cerrada por obras.
- **Soporte Opcional de API de Transporte GCBA**:
  - Permite ingresar opcionalmente `client_id` y `client_secret` de la API de Transporte de CABA (`apitransporte.buenosaires.gob.ar`) en el Paso 2 de configuración para sumar pronósticos GTFS-RT de Subte por estación.

---

## 🛤️ Líneas y Estaciones Soportadas

| Red | Líneas disponibles | Estaciones georreferenciadas |
| :--- | :--- | :--- |
| **Subte y Premetro (Emova)** | `A`, `B`, `C`, `D`, `E`, `H`, `Premetro` | 98 estaciones |
| **Trenes Metropolitanos (AMBA)** | `Sarmiento`, `Mitre`, `Roca`, `San Martín`, `Belgrano Sur`, `Belgrano Norte`, `Urquiza`, `Tren de la Costa` | 265 estaciones |

---

## 📦 Instalación

### Opción 1: Mediante HACS (Recomendado)

1. Abrí **HACS** en tu instancia de Home Assistant.
2. Hacé clic en el menú de tres puntos (arriba a la derecha) y seleccioná **Repositorios personalizados** (*Custom repositories*).
3. Agregá la URL `https://github.com/Lean724/transportes_ba` con la categoría **Integración** (*Integration*).
4. Buscá **Transportes de Buenos Aires** e instalalo.
5. Reiniciá Home Assistant.

### Opción 2: Instalación Manual

1. Descargá este repositorio y copiá la carpeta `custom_components/transportes_ba` dentro del directorio `/config/custom_components/` de tu Home Assistant.
2. Reiniciá Home Assistant.

---

## ⚙️ Configuración en 2 Pasos

1. En Home Assistant, andá a **Ajustes > Dispositivos y Servicios > + Añadir integración** y buscá **Transportes de Buenos Aires**.
2. **Paso 1 (Redes, Líneas y Radio)**:
   - Seleccioná las líneas de Subte y Tren que quieras monitorear.
   - Indicá si querés monitorear estaciones cercanas y el radio en kilómetros desde tu casa (por defecto `2.0 km`).
3. **Paso 2 (Estaciones Cercanas y API Opcional)**:
   - Verás pre-seleccionadas las estaciones encontradas dentro de tu radio, ordenadas por distancia (ej. `Tren Sarmiento - Caballito (0.6 km)`). Podés agregar o quitar cualquier otra estación.
   - Opcionalmente, podés completar `API GCBA Client ID` y `Client Secret`.

---

## 📊 Entidades Creadas

### 1. Sensores de Línea (`sensor`)

| Entidad de ejemplo | Estado (`state`) | Atributos (`extra_state_attributes`) |
| :--- | :--- | :--- |
| `sensor.subte_linea_b` | `"Normal"` o motivo directo (ej. `"Estación Medrano cerrada por obras..."`) | `categoria`, `alerta_operativa`, `mensaje`, `frecuencia`, `actualizado` |
| `sensor.tren_sarmiento` | `"Normal"` o motivo directo del problema/alerta | `categoria`, `alerta_operativa`, `mensaje`, `ramales` |

### 2. Sensores de Estación Cercana / Próximos Trenes (`sensor`)

| Entidad de ejemplo | Estado (`state`) | Atributos (`extra_state_attributes`) |
| :--- | :--- | :--- |
| `sensor.estacion_caballito_sarmiento` | `"Once: 4 min, 14 min \| Moreno: 7 min"` | `distancia_casa_km`, `estacion_cerrada`, `proximo_servicio`, `arribos` (destino, minutos, andén, ramal, hora estimada), `latitud`, `longitud` |
| `sensor.estacion_almagro_medrano_subte_b` | `"Operativa (cada 6 min)"` o `"Cerrada: Estación Medrano cerrada por obras..."` | `distancia_casa_km`, `estacion_cerrada`, `frecuencia_linea`, `arribos`, `alerta_linea` |

### 3. Sensores Binarios de Incidencia Operativa (`binary_sensor`)

| Entidad de ejemplo | Clase de dispositivo | Valor |
| :--- | :--- | :--- |
| `binary_sensor.subte_linea_b_alerta` | `problem` | `on` solo ante problema operativo real (`demoras`, `servicio_limitado`, `interrumpido`); `off` en servicio normal o avisos informativos |
| `binary_sensor.tren_sarmiento_alerta` | `problem` | `on` solo ante problema operativo real; `off` en servicio normal o avisos informativos |
