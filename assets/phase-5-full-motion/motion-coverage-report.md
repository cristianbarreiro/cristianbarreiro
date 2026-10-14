# Phase 5 — Full banner motion coverage

## Resultado

- Composición: 1672 × 941, 30 fps, 9 segundos, 270 fotogramas.
- Capa base: la imagen original se mantiene intacta. El PNG estático se copió byte por byte y coincide con el origen en píxeles: **True**.
- SHA-256 del origen: `50d22010771a31d20a9bdd051d2b0baff121fa723fb8b28f99e3c0c408821c8f`.
- SHA-256 de la copia estática: `50d22010771a31d20a9bdd051d2b0baff121fa723fb8b28f99e3c0c408821c8f`.
- Efectos añadidos sobre la composición heredada: 28 capas (23 pulsos y 5 barridos luminosos).
- La animación se mantiene como capas raster con transparencia. No se afirma que el banner original se haya convertido en vectores editables.

## Regiones preparadas

- Anillo luminoso grande: selección cromática limitada a píxeles existentes dentro de una banda circular.
- Perímetro de la insignia CB: selección cromática de los píxeles visibles del borde; letras excluidas.
- Borde visible del panel terminal: segmentos superior, izquierdo y derecho; partes ocultas por la insignia o el botón no se reconstruyen.
- Tres indicadores de estado del terminal: máscaras separadas por color.
- Campo de puntos superior izquierdo: 45 componentes de origen aislados.
- Campo de puntos inferior derecho: 32 componentes de origen aislados.
- Cinco trazos periféricos: solo los píxeles cromáticos dentro de corredores ajustados a líneas visibles.
- Trazos superiores y borde del botón: capas heredadas de Phase 4, conservadas sin alterar el arte base.

### Cobertura de barridos sobre píxeles fuente

| Trazo | Cobertura medida | Barrido móvil |
|---|---:|---:|
| mid-left-trace-sweep | 100% | sí |
| lower-upper-trace-sweep | 100% | sí |
| lower-stepped-trace-sweep | 100% | sí |
| lower-node-trace-sweep | 100% | sí |
| lower-accent-sweep | 100% | sí |

La cobertura se estima muestreando el recorrido y comprobando que cada punto cae cerca de píxeles fuente seleccionados. Los trazos bajo texto, iconos, paneles o botones no se prolongan por zonas ocultas.

## Límites pendientes

- El cursor del terminal y el texto del terminal siguen dentro de la imagen base; no se aíslan ni animan.
- Tipografía, iconos, contenido del botón y el resto del banner permanecen como raster estático.
- Los bordes ocultos del panel y los segmentos tapados de circuitos no se reconstruyen.
- Las máscaras realzan píxeles de color existentes; no crean rutas vectoriales independientes.
- No se abrió un navegador ni LottieFiles Creator. El JSON y las imágenes se prepararon localmente; falta validar su render dentro de esa plataforma.
- La salida SVG usa SMIL (`animate` / `animateMotion`); su reproducción depende del visor. El JSON Lottie es el formato principal de intercambio.

## Archivos

- `profile-banner-phase-5.json`: Lottie autocontenido con imágenes inline.
- `lottie/images/`: PNGs auxiliares transparentes para inspección y flujo con assets separados.
- `profile-banner-phase-5-animated.svg`: SVG autocontenido con efectos SMIL.
- `profile-banner-phase-5-static-preview.png`: copia estática exacta del origen.
- `preview/profile-banner-phase-5-animation-preview.gif`: previsualización animada de 9 segundos.
- `preview/animation-contact-sheet.jpg`: cinco instantes de la animación.
- `preview/initial-selection-audit.jpg`: auditoría visual de las máscaras seleccionadas.
