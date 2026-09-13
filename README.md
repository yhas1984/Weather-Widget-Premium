# Weather Widget

Widget de escritorio premium para Linux (X11 y Wayland) con datos de Open-Meteo.

![Weather Widget](icon.png)

## Características

| Feature | Descripción |
|---------|-------------|
| **Iconos vectoriales** | Sol, luna, nubes, lluvia, nieve y tormenta sin emojis del sistema |
| **Clima en tiempo real** | Open-Meteo como proveedor principal, con reintentos y validación de respuesta |
| **Geolocalización** | Ciudad exacta guardada o detección por IP opcional; nunca sustituye silenciosamente otra ciudad |
| **Buscador de ciudades** | Autocompletado con ciudad, región, país y coordenadas exactas |
| **Expandible** | Clic para ver humedad, viento y sensación térmica |
| **Glassmorphism** | Opacidad de fondo de 0–80% y temas Atmospheric, Glass, Minimal y Pearl |
| **Arrastrable** | Mover el widget con el ratón |
| **Auto-inicio** | Se ejecuta automáticamente al iniciar sesión |
| **Forecast completo** | Previsión horaria y diaria expandible sin clipping |
| **Red no bloqueante** | Las consultas se ejecutan fuera del hilo de interfaz |
| **Unidades reales** | Cambio entre °C/km/h/mm y °F/mph/in desde el menú contextual |

## Requisitos

- Python 3.8+
- PyQt6
- requests
- Linux (GNOME, KDE o similar)

## Instalación rápida

```bash
git clone https://github.com/yhas1984/Weather-Widget.git
cd Weather-Widget
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run_v6.py
```

## Uso

```bash
python run_v6.py
```

El widget aparecerá en la esquina inferior derecha de la pantalla.

### Interacciones

| Acción | Efecto |
|--------|--------|
| **Clic** | Expandir/colapsar detalles |
| **Arrastrar** | Mover widget |
| **Clic derecho** | Menú de opciones |
| **Cambiar ciudad** | Menú contextual → Cambiar Ciudad |

## APIs Meteorológicas

| API | Prioridad | Descripción |
|-----|-----------|-------------|
| Open-Meteo | Principal | Clima actual y previsiones; selección automática del mejor modelo disponible |
| GeoNames | Geocodificación | Base de datos utilizada por el buscador de Open-Meteo |
| ipapi.co | Opcional | Ubicación aproximada por IP cuando no se ha elegido una ciudad |

El porcentaje mostrado como **Prob. 1 h** es la probabilidad prevista para la próxima hora, no una medición de lluvia actual. Las respuestas se validan antes de mostrarse, se reintentan los fallos transitorios y se conserva una caché independiente por ubicación y sistema de unidades durante un máximo de 24 horas.

La ubicación automática por IP se puede desactivar desde el menú contextual. Si está desactivada o falla, el widget conserva los últimos datos válidos o solicita elegir una ciudad; no utiliza una ciudad predeterminada ficticia.

## Iconos

El repositorio incluye múltiples versiones del icono:

| Archivo | Descripción |
|---------|-------------|
| `icon.png` | Icono principal (sol + nube + lluvia) |
| `icon.svg` | Versión SVG del icono principal |
| `icon-minimal.png` | Versión minimalista |
| `icon-clean.png` | Versión limpia y moderna |

## Estructura

```
Weather-Widget/
├── run_v6.py            # Lanzador actual
├── weather_widget_v6/   # Modelos, red, integración Linux y UI premium
├── weather_widget.py    # Implementación histórica V5
├── requirements.txt     # Dependencias
├── icon.png             # Icono principal
├── icon.svg             # Icono SVG
├── icon-minimal.png     # Icono minimalista
├── icon-clean.png       # Icono limpio
└── .gitignore
```

## Solución de problemas

**Error de Qt platform plugin:**
```bash
sudo apt install libxcb-xinerama0
```

**Error de API:**
El widget conserva el último estado válido en caché y lo muestra si Open-Meteo no está disponible.

## Instalación desde `.deb`

Los paquetes compilados se publican como assets en la sección [Releases](https://github.com/yhas1984/Weather-Widget/releases). Descarga el archivo `weather-widget_*_amd64.deb` y ejecuta:

```bash
sudo apt install ./weather-widget_*_amd64.deb
```

La API pública de Open-Meteo funciona sin credenciales para uso no comercial dentro de sus límites. La atribución a Open-Meteo y a sus fuentes de datos es obligatoria; una distribución comercial debe usar el plan/licencia correspondiente. En X11 se aplican hints EWMH de escritorio; en Wayland el comportamiento exacto de “Mostrar escritorio” depende del compositor.

## Compilar el `.deb`

```bash
python -m pip install -r requirements.txt
bash packaging/build-deb.sh 6.0.0
```

El paquete detecta automáticamente la plataforma Qt disponible y no fuerza XCB bajo Wayland.

## Licencia

MIT
