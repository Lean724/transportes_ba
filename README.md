# 🚇🚆 Transportes de Buenos Aires (`transportes_ba`)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/Lean724/transportes_ba)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Integración personalizada (`custom_component`) para **Home Assistant** que monitorea en tiempo real el estado del servicio, frecuencias y alertas de la red de **Subte y Premetro (Emova)** y **Trenes Metropolitanos del AMBA (Trenes Argentinos / SOFSE)**.

---

## ✨ Características

- **Configuración 100% por interfaz gráfica (`ConfigFlow` y `OptionsFlow`)**: Seleccioná qué redes habilitar y qué líneas específicas querés monitorear sin editar archivos YAML. Podés reconfigurar las líneas en cualquier momento desde **Configurar**.
- **Coordinadores independientes**: La red de Subte (sondeo cada 3 minutos) y la de Trenes (sondeo cada 5 minutos) utilizan `DataUpdateCoordinator` independientes. Una caída en un proveedor no afecta la disponibilidad del otro.
- **Conexión en tiempo real**:
  - **Subte y Premetro**: Consulta el servicio en tiempo real de **Emova** (`info.emova.com.ar`) con soporte de respaldo JSON.
  - **Trenes Argentinos**: Consulta el estado de gerencias, alertas activas y ramales operativos de **SOFSE** (`api-servicios.sofse.gob.ar/v1`) con renovación automática de credenciales temporales.
- **Sensores de estado y sensores binarios de alerta**: Cada línea seleccionada expone un `sensor` con el estado operativo (más atributos detallados) y un `binary_sensor` (`device_class: problem`) ideal para disparar notificaciones y automatizaciones.

---

## 🛤️ Líneas Soportadas

| Red | Líneas disponibles |
| :--- | :--- |
| **Subte y Premetro (Emova)** | `A`, `B`, `C`, `D`, `E`, `H`, `Premetro` |
| **Trenes Metropolitanos (AMBA)** | `Sarmiento`, `Mitre`, `Roca`, `San Martín`, `Belgrano Sur`, `Belgrano Norte`, `Urquiza`, `Tren de la Costa` |

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

## ⚙️ Configuración

1. En Home Assistant, andá a **Ajustes > Dispositivos y Servicios**.
2. Hacé clic en **+ Añadir integración** y buscá **Transportes de Buenos Aires**.
3. Marcá las redes que quieras habilitar (**Subte** y/o **Trenes**) y elegí en el menú desplegable las líneas que usás habitualmente.
4. Para agregar o quitar líneas más adelante, entrá a la integración y presioná **Configurar**.

---

## 📊 Entidades Creadas

Por cada línea seleccionada se crean dos entidades agrupadas bajo su respectivo dispositivo de servicio (`Red de Subte y Premetro (Emova)` o `Trenes Metropolitanos (AMBA)`):

### 1. Sensores de Estado (`sensor`)

| Entidad de ejemplo | Estado (`state`) | Atributos (`extra_state_attributes`) |
| :--- | :--- | :--- |
| `sensor.subte_linea_a` | `Normal`, `Demoras`, `Servicio limitado`, `Con modificaciones`, `Interrumpido` | `mensaje`, `frecuencia` (ej. `6 min`), `actualizado` |
| `sensor.tren_sarmiento` | `Normal`, `Alerta activa`, `Demoras`, `Servicio limitado`, `Interrumpido` | `mensaje`, `ramales` (lista de ramales con estado y alertas) |

### 2. Sensores Binarios de Incidencia (`binary_sensor`)

| Entidad de ejemplo | Clase de dispositivo | Valor |
| :--- | :--- | :--- |
| `binary_sensor.subte_linea_a_alerta` | `problem` | `off` = Servicio normal / `on` = Problema o alerta activa |
| `binary_sensor.tren_sarmiento_alerta` | `problem` | `off` = Servicio normal / `on` = Problema o alerta activa |

---

## 🤖 Ejemplo de Automatización

Recibí una notificación en tu celular si la Línea D o el Tren Mitre presentan demoras o interrupciones antes de salir de casa:

```yaml
alias: "Alerta de Transporte en Hora Pico"
description: "Notifica si hay problemas en el Subte D o Tren Mitre por la mañana"
trigger:
  - platform: state
    entity_id:
      - binary_sensor.subte_linea_d_alerta
      - binary_sensor.tren_mitre_alerta
    from: "off"
    to: "on"
condition:
  - condition: time
    after: "07:00:00"
    before: "10:00:00"
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri
action:
  - service: notify.notify
    data:
      title: "⚠️ Alerta en {{ trigger.to_state.name }}"
      message: >-
        Estado: {{ state_attr(trigger.entity_id, 'estado') }}.
        {{ state_attr(trigger.entity_id, 'mensaje') }}
mode: queued
```

---

## 🗂️ Estructura del Proyecto

```text
custom_components/transportes_ba/
├── __init__.py               # Setup de la integración, recarga de opciones y coordinadores
├── manifest.json             # Metadatos del componente e información HACS
├── const.py                  # Constantes, dominios, endpoints y mapeos SOFSE
├── config_flow.py            # ConfigFlow y OptionsFlow por UI (selección modular)
├── coordinator.py            # Clases DataUpdateCoordinator para Subte y Trenes
├── sensor.py                 # Plataforma de sensores (CoordinatorEntity)
├── binary_sensor.py          # Sensores binarios de servicio normal / con problema
├── strings.json              # Textos base de configuración y opciones
└── translations/
    ├── es.json               # Traducción al español
    └── en.json               # Traducción al inglés
```
