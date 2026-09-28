# Skull Mining: plugin de EDMC para la flota Skull (v0.5.3)

Registra automáticamente las sesiones de minería en superficie con el Rhino y las envía a una hoja de Google compartida por la flota. De cada sesión calcula:

- **Taladros**: cuántos se colocaron (las recogidas se agrupan por posición) y cuántas veces se recogió cada uno.
- **Distancias**: la distancia media y mínima entre taladros, y la ruta de recogida más corta que pasa por todos.
- **Orografía**: la velocidad efectiva entre taladros, y la sinuosidad (recorrido real ÷ línea recta), con una etiqueta **llano / ondulado / montañoso**.
- **Rendimiento**: toneladas por mineral, valor estimado y Cr/hora.

La hoja organiza todo por **sitio**: un depósito de un solo mineral (la mancha morada del escáner), que puede medir más de 100 m. Los taladros del mismo mineral a menos de 150 m forman un sitio, y las sesiones de todos los miembros se juntan en el mismo sitio si caen a menos de 150 m. En la pestaña **Sitios** se ve el mineral, su precio, el **máximo de taladros** que ha conseguido alguien, la distancia mínima entre taladros, la extensión y el **valor por vuelta** (taladros × t por recogida × precio), que es la cifra para comparar sitios. También aparece la distancia al sitio más cercano (de cualquier mineral y del mismo mineral) y el terreno de la zona.

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
- **El juego no escribe eventos al poner o recoger taladros.** Cada recogida es una ráfaga de unas 11-12 t de `MiningRefined` (1 evento = 1 t) en unos 14 s. Los taladros se cuentan agrupando esas ráfagas por posición y mineral. Cada taladro dio un solo mineral.
- Al mapear un cuerpo, `SAASignalsFound` indica cuántos sitios de minería tiene ("Planetary Mining Location").
- Al aterrizar, `Touchdown` dice en qué sitio estás ("Planetary Mining Location Signal (3)"). La hoja usa ese número para identificar el sitio.
- Dentro del SRV la altitud es siempre 0: **no se puede medir el desnivel**. La orografía se calcula con la velocidad real y la sinuosidad.
- Cada recogida da también materiales en bruto (`MaterialCollected`), que se guardan en la sesión.
- Pasar la carga a la nave (`CargoTransfer`) queda registrado como "carga a nave".

Distancia mínima entre taladros: **unos 47 m**. Frontier no la ha publicado; es la que se consiguió apurando al máximo en un sitio de Torio (27-sep-2026). Por eso el plugin considera que dos recogidas a menos de 23,5 m (la mitad) son el mismo taladro. La hoja guarda la mínima observada en cada sitio, por si algún miembro consigue menos.

Pendiente de calibrar con más sesiones: los umbrales de velocidad y sinuosidad de llano, ondulado y montañoso.

## 5. Zonas de minería, densidad y sitios agotados

- **Zonas:** cada planeta tiene varias zonas (las señales "Planetary Mining Location Signal (N)"). Cuando fijas una zona como destino, el plugin lo apunta y lo **recuerda** aunque quites el destino o reinicies EDMC. Al bajar guarda el punto de la zona, y a cada sitio que mines le asigna su zona. Si falta el número, la hoja usa la zona conocida más cercana (hasta 10 km). **Si el plugin no sabe en qué zona estás, la línea de Skull Mining se pone naranja** con el aviso "Zona desconocida": fija la zona como destino (mapa del planeta o panel izquierdo) y el aviso desaparece.
- **Minerales de la zona:** el juego solo los muestra en pantalla al fijar la zona. Apúntalos a mano en la pestaña **Zonas** de la hoja, columna "Minerales (anotar a mano)", separados por comas. La hoja rellena sola los "Minerales confirmados" con lo que ha minado la flota.
- **Densidad y cantidad:** el escáner del Rhino muestra dos datos que el juego no escribe en el journal: **Density** (fija) y **Mineral amount** (lo que queda; baja a medida que mina cualquier jugador). En la ventana de EDMC hay dos filas de botones: **Densidad** (Alta, Media, Baja) y **Cantidad** (Alta, Media, Baja, Agotado). Púlsalos **estando en el sitio**. Al marcar la cantidad se guardan las toneladas que la flota llevaba sacadas del sitio, para estimar cuánto aguanta. Si marcas una cantidad en un sitio que figuraba como agotado, deja de figurar como agotado.

- **Datos en bruto:** desde la v0.5.0 cada sesión envía también la hora, posición y zona de cada tonelada refinada (pestaña **Recogidas**). Así, si mejoramos los cálculos, se pueden rehacer las sesiones sin volver a minar.
- **Novedades del juego:** si Frontier añade eventos o campos nuevos de minería al journal (por ejemplo el depósito o su desgaste), el plugin los envía a la pestaña **Eventos** y Discord avisa la primera vez.

## 6. Avisos en Discord

La hoja puede avisar en un canal de Discord de la flota:
1. En Discord: **Editar canal → Integraciones → Webhooks → Nuevo webhook** ("Skull Mining") → **Copiar URL**. No la publiques.
2. En Apps Script: **Configuración del proyecto → Propiedades del script → Añadir propiedad**: `DISCORD_WEBHOOK` = la URL copiada.
3. Ejecuta la función **probarDiscord** desde el editor: debe llegar un mensaje de prueba al canal.

Opciones (también en Propiedades del script):
- `DISCORD_MODE`: `novedades` (por defecto; avisa de un sitio nuevo o de un récord de taladros), `sesiones` (además, cada sesión en un sitio conocido) o `no`.
- `DISCORD_ESTADOS`: `si` para avisar también cuando alguien marca un sitio como Agotado.
