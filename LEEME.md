# Skull Mining: plugin de EDMC para la flota Skull (v0.3.3)

Registra automáticamente las sesiones de minería en superficie con el Rhino y las envía a una hoja de Google compartida por la flota. De cada sesión calcula:

- **Plataformas**: cuántas se colocaron (las recogidas se agrupan por posición) y cuántas veces se recogió cada una.
- **Distancias**: la distancia media y mínima entre plataformas, y la ruta de recogida más corta que pasa por todas.
- **Orografía**: la velocidad efectiva entre plataformas, y la sinuosidad (recorrido real ÷ línea recta), con una etiqueta **llano / ondulado / montañoso**.
- **Rendimiento**: toneladas por mineral, valor estimado y Cr/hora.

La hoja organiza todo por **sitio**: una zona de un solo mineral de unos 50 m como mucho. Las plataformas del mismo mineral a menos de 60 m forman un sitio, y las sesiones de todos los miembros se juntan en el mismo sitio si caen a menos de 60 m. En la pestaña **Sitios** se ve el mineral, su precio, el **máximo de plataformas** que ha conseguido alguien, la distancia mínima entre plataformas, la extensión y el **valor por vuelta** (plataformas × t por recogida × precio), que es la cifra para comparar sitios. También aparece la distancia al sitio más cercano (de cualquier mineral y del mismo mineral) y el terreno de la zona.

---

## 1. Montar la hoja de la flota (solo el administrador, una vez)

1. Crea una hoja de cálculo nueva en Google Drive, por ejemplo "Skull Mining".
2. Abre **Extensiones → Apps Script**, borra el contenido y pega `Code.gs`. Guarda.
3. En el desplegable de funciones elige **setup** y pulsa **Ejecutar**. Acepta los permisos. Se crean las pestañas y la tabla de precios, y se genera una **clave de la flota**. La clave aparece en el registro de ejecución y en *Configuración del proyecto → Propiedades del script → FLEET_TOKEN*.
4. Pulsa **Implementar → Nueva implementación → Tipo: Aplicación web**, con *Ejecutar como: Yo* y *Quién tiene acceso: Cualquier usuario*. Copia la **URL** que termina en `/exec`.
5. Pasa a la flota la **URL** y la **clave**. Compártela solo con los miembros: con ellas cualquiera puede enviar datos.

Para cambiar la clave, edita `FLEET_TOKEN` en las propiedades del script. Si cambias el código, publica una **nueva versión** en *Implementar → Gestionar implementaciones* para que la URL no cambie.

## 2. Instalar el plugin (cada miembro)

1. En EDMC: **Archivo → Ajustes → Plugins → Abrir** (la carpeta de plugins).
2. Copia dentro la carpeta `SkullMining` completa y reinicia EDMC.
3. En **Ajustes → Skull Mining**, pega la URL y la clave de la flota. El alias es opcional.
4. En la ventana principal de EDMC aparece la línea "Skull Mining", que muestra el estado.

## 3. Qué se envía

- **Sesiones en superficie en las que has refinado algo**: el recorrido del Rhino, la posición de las recogidas, las toneladas y la información del planeta. Si no refinas nada, no se envía nada.
- **Ventas** de minerales de superficie (precio real).
- **Datos de cuerpos** al mapearlos con la sonda (tipo, gravedad, temperatura y señales).
- **Eventos nuevos del journal** relacionados con minería o el Rhino que el plugin aún no conoce. Esto sirve para mejorarlo.

Si pones un alias, se usa en lugar de tu nombre de comandante. Si no hay conexión, todo queda guardado en `pending.json` y se reenvía después.

## 4. Qué se sabe de una sesión real (27-sep-2026) y qué falta

Comprobado con una sesión real con el Rhino en Pegasi Sector JN-S b4-7 B 4 a:
- El Rhino cuenta como SRV para el juego (`SRVType: mev_rhino`), así que el recorrido se graba.
- **El juego no escribe eventos al poner o recoger plataformas.** Cada recogida es una ráfaga de unas 11-12 t de `MiningRefined` (1 evento = 1 t) en unos 14 s. Las plataformas se cuentan agrupando esas ráfagas por posición y mineral. Cada plataforma dio un solo mineral.
- Al mapear un cuerpo, `SAASignalsFound` indica cuántos sitios de minería tiene ("Planetary Mining Location").
- Al aterrizar, `Touchdown` dice en qué sitio estás ("Planetary Mining Location Signal (3)"). La hoja usa ese número para identificar el sitio.
- Dentro del SRV la altitud es siempre 0: **no se puede medir el desnivel**. La orografía se calcula con la velocidad real y la sinuosidad.
- Cada recogida da también materiales en bruto (`MaterialCollected`), que se guardan en la sesión.
- Pasar la carga a la nave (`CargoTransfer`) queda registrado como "carga a nave".

Distancia mínima entre plataformas: **unos 47 m**. Frontier no la ha publicado; es la que se consiguió apurando al máximo en un sitio de Torio (27-sep-2026). Por eso el plugin considera que dos recogidas a menos de 23,5 m (la mitad) son la misma plataforma. La hoja guarda la mínima observada en cada sitio, por si algún miembro consigue menos.

Pendiente de calibrar con más sesiones: los umbrales de velocidad y sinuosidad de llano, ondulado y montañoso.
