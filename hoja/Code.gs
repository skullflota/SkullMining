/**
 * Skull Mining - receptor de datos de la flota (Google Apps Script).
 *
 * Instalación (una sola vez, la hace el administrador):
 *   1. Crear una Hoja de cálculo de Google nueva → Extensiones → Apps Script.
 *   2. Pegar este archivo como Code.gs y guardar.
 *   3. Ejecutar la función `setup` (pedirá permisos). Crea las pestañas y una clave.
 *      La clave aparece en el registro de ejecución y en Configuración del proyecto →
 *      Propiedades del script → FLEET_TOKEN.
 *   4. Implementar → Nueva implementación → Aplicación web.
 *      Ejecutar como: Yo. Quién tiene acceso: Cualquier usuario.
 *   5. Pasar a la flota la URL de la aplicación web y la clave.
 */

var SITE_MATCH_M = 60;   // un sitio (un solo mineral) mide ~50 m como mucho
var TRACK_CHUNK = 45000; // límite práctico por celda

var HEADERS = {
  'Sitios': ['SiteID', 'Sistema', 'Cuerpo', 'Mineral', 'Nombre interno', 'Precio (Cr)', 'Lat', 'Lon',
             'Máx plataformas', 'Dist. mín entre plataformas (m)', 'Extensión (m)', 'T/recogida',
             'Valor por vuelta (Cr)', 'Visitas', 'Recogidas', 'Toneladas totales', 'Sitio más cercano (m)',
             'Mismo mineral más cercano (m)', 'Terreno zona', 'Vel. efectiva zona (m/s)', 'Señal zona',
             'Sitios minería en cuerpo', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Última visita', 'Último CMDR'],
  'Visitas': ['SessionID', 'SiteID', 'Fecha', 'CMDR', 'Mineral', 'Plataformas', 'Dist. mín entre plataformas (m)',
              'Extensión (m)', 'Recogidas', 'Toneladas', 'T/recogida', 'Terreno zona', 'Vel. efectiva zona (m/s)'],
  'Sesiones': ['SessionID', 'Sitios', 'Recibido', 'CMDR', 'Sistema', 'Cuerpo', 'Inicio', 'Fin', 'Duración (min)',
               'Plataformas', 'Recogidas', 'T/recogida', 'Ciclo recogida (min)', 'Señal zona',
               'Sitios minería en cuerpo', 'Materiales', 'Cargas a nave (t)', 'Toneladas', 'Valor estimado (Cr)',
               'Cr/h', 'Ruta recogida (m)', 'Vel. efectiva (m/s)', 'Vel. en movimiento (m/s)', 'Sinuosidad',
               'Terreno', 'Recorrido (m)', 'Minerales', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Radio (m)',
               'Vehículo', 'Motivo cierre', 'Eventos desconocidos', 'Versión plugin'],
  'Plataformas': ['SessionID', 'SiteID', 'Nº', 'Lat', 'Lon', 'Mineral', 'Toneladas', 'Recogidas', 'T/recogida',
                  'Primera', 'Última'],
  'Tramos': ['SessionID', 'De', 'A', 'Línea recta (m)', 'Recorrido (m)', 'Tiempo (s)',
             'Vel. efectiva (m/s)', 'Sinuosidad'],
  'Recorridos': ['SessionID', 'Parte', 'Datos (t,lat,lon,alt;...)'],
  'Cuerpos': ['Sistema', 'Cuerpo', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Radio (m)', 'Atmósfera',
              'Distancia (ls)', 'Sitios de minería', 'Señales', 'Actualizado', 'CMDR'],
  'Ventas': ['Fecha', 'CMDR', 'Tipo', 'Nombre', 'Cantidad', 'Precio venta', 'Total', 'Sistema', 'MarketID'],
  'Eventos': ['Fecha', 'CMDR', 'Evento', 'Sistema', 'Cuerpo', 'Lat', 'Lon', 'JSON'],
  'Precios': ['Tipo (interno)', 'Nombre ES', 'Nombre EN', 'Precio medio (Cr)', 'Interno verificado']
};

var PRICE_SEED = [
  ['monazite', 'Monacita', 'Monazite', 270000], ['alexandrite', 'Alejandrita', 'Alexandrite', 229000],
  ['grandidierite', 'Grandidierita', 'Grandidierite', 213000], ['iridium', 'Iridio', 'Iridium', 212000],
  ['periclasedunite', 'Dunita de periclasa', 'Periclase Dunite', 206000], ['thortveitite', 'Thortveitita', 'Thortveitite', 206000],
  ['serendibite', 'Serendibita', 'Serendibite', 188000], ['rhodplumsite', 'Rhodplumsita', 'Rhodplumsite', 187000],
  ['diamond', 'Diamante', 'Diamond', 136000], ['lowtemperaturediamond', 'Diamantes de baja temp.', 'Low Temperature Diamonds', 130000],
  ['sapphire', 'Zafiro', 'Sapphire', 129000], ['ruby', 'Rubí', 'Ruby', 111000], ['helium', 'Helio', 'Helium', 104000],
  ['helium3', 'Helio-3', 'Helium-3', 97000], ['bastnasite', 'Bastnasita', 'Bastnasite', 80000],
  ['platinum', 'Platino', 'Platinum', 71000], ['osmium', 'Osmio', 'Osmium', 56000], ['tritium', 'Tritio', 'Tritium', 53000],
  ['palladium', 'Paladio', 'Palladium', 52000], ['gold', 'Oro', 'Gold', 47000],
  ['quartzpyroxenite', 'Piroxenita de cuarzo', 'Quartz Pyroxenite', 47000], ['jadeite', 'Jadeíta', 'Jadeite', 42000],
  ['deuterium', 'Deuterio', 'Deuterium', 41000], ['magnesite', 'Magnesita', 'Magnesite', 38000],
  ['silver', 'Plata', 'Silver', 37000], ['olivine', 'Olivino', 'Olivine', 32000], ['samarium', 'Samario', 'Samarium', 28000],
  ['tantalum', 'Tantalio', 'Tantalum', 14000], ['thorium', 'Torio', 'Thorium', 12000], ['uranium', 'Uranio', 'Uranium', 7000],
  ['titanium', 'Titanio', 'Titanium', 4000], ['uraninite', 'Uraninita', 'Uraninite', 3000],
  ['methanolmonohydratecrystals', 'Cristales de metanol', 'Methanol Monohydrate Crystals', 2000],
  ['hematite', 'Hematita', 'Hematite', 2000], ['lithium', 'Litio', 'Lithium', 2000], ['copper', 'Cobre', 'Copper', 700],
  ['water', 'Agua', 'Water', 496]
];

// ------------------------------------------------------------------- instalación
function setup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  Object.keys(HEADERS).forEach(function (name) {
    var sh = ss.getSheetByName(name) || ss.insertSheet(name);
    if (sh.getLastRow() === 0) {
      sh.appendRow(HEADERS[name]);
      sh.setFrozenRows(1);
      sh.getRange(1, 1, 1, HEADERS[name].length).setFontWeight('bold').setBackground('#fff2cc');
    }
  });
  var precios = ss.getSheetByName('Precios');
  if (precios.getLastRow() === 1) {
    precios.getRange(2, 1, PRICE_SEED.length, 5).setValues(PRICE_SEED.map(function (r) { return r.concat(['no']); }));
  }
  var def = ss.getSheetByName('Hoja 1') || ss.getSheetByName('Sheet1');
  if (def && def.getLastRow() === 0 && ss.getSheets().length > 1) ss.deleteSheet(def);

  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty('FLEET_TOKEN')) {
    props.setProperty('FLEET_TOKEN', Utilities.getUuid().replace(/-/g, '').slice(0, 16));
  }
  Logger.log('Clave de la flota: ' + props.getProperty('FLEET_TOKEN'));
}

// ---------------------------------------------------------------------- entrada
function doPost(e) {
  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: 'json' });
  }
  var token = PropertiesService.getScriptProperties().getProperty('FLEET_TOKEN');
  if (!body || body.token !== token) return json_({ ok: false, error: 'token' });

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var d = body.data || {};
    switch (body.kind) {
      case 'session': handleSession_(d); break;
      case 'sale': handleSale_(d); break;
      case 'body': handleBody_(d); break;
      case 'event': handleEvent_(d); break;
      default: return json_({ ok: false, error: 'kind' });
    }
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
  return json_({ ok: true });
}

// Lectura de sitios para el futuro visor: ?token=...&sheet=Sitios
function doGet(e) {
  var p = (e && e.parameter) || {};
  // Lectura pública para la web del ranking: solo sitios, sin nombres de comandante
  if (p.view === 'ranking') return publicRanking_(p.callback);
  var token = PropertiesService.getScriptProperties().getProperty('FLEET_TOKEN');
  if (!e || !e.parameter || e.parameter.token !== token) return json_({ ok: false, error: 'token' });
  var name = e.parameter.sheet || 'Sitios';
  if (['Sitios', 'Visitas', 'Sesiones', 'Plataformas', 'Tramos', 'Precios'].indexOf(name) < 0) return json_({ ok: false, error: 'sheet' });
  var values = sheet_(name).getDataRange().getValues();
  var head = values.shift();
  var rows = values.map(function (r) { var o = {}; head.forEach(function (h, i) { o[h] = r[i]; }); return o; });
  return json_({ ok: true, rows: rows });
}

var PUBLIC_SITE_FIELDS = {
  'SiteID': 'id', 'Sistema': 'system', 'Cuerpo': 'body', 'Mineral': 'mineral', 'Nombre interno': 'type',
  'Precio (Cr)': 'price', 'Lat': 'lat', 'Lon': 'lon', 'Máx plataformas': 'rigs',
  'Dist. mín entre plataformas (m)': 'rigSpacing', 'Extensión (m)': 'extent', 'T/recogida': 'tpc',
  'Valor por vuelta (Cr)': 'value', 'Visitas': 'visits', 'Recogidas': 'collections',
  'Toneladas totales': 'tonnes', 'Sitio más cercano (m)': 'nearest', 'Mismo mineral más cercano (m)': 'nearestSame',
  'Terreno zona': 'terrain', 'Vel. efectiva zona (m/s)': 'speed', 'Señal zona': 'signal',
  'Sitios minería en cuerpo': 'bodySites', 'Tipo planeta': 'planetClass', 'Gravedad (g)': 'gravity',
  'Temp (K)': 'temp', 'Última visita': 'lastVisit'
};

function publicRanking_(callback) {
  var values = sheet_('Sitios').getDataRange().getValues();
  var head = values.shift();
  var sites = values.filter(function (r) { return r[0]; }).map(function (r) {
    var o = {};
    head.forEach(function (h, i) {
      var k = PUBLIC_SITE_FIELDS[h];
      if (!k) return;
      var v = r[i];
      if (v instanceof Date) v = v.toISOString();
      o[k] = v === '' ? null : v;
    });
    return o;
  });
  var ses = sheet_('Sesiones').getDataRange().getValues().slice(1);
  var cmdrs = {};
  var tonnes = 0;
  ses.forEach(function (r) { if (r[3]) cmdrs[r[3]] = 1; tonnes += Number(r[17]) || 0; });
  var out = { ok: true, updated: new Date().toISOString(), sites: sites,
              stats: { sites: sites.length, sessions: ses.length, commanders: Object.keys(cmdrs).length, tonnes: tonnes } };
  var txt = JSON.stringify(out);
  if (callback && /^[A-Za-z_$][\w$.]{0,60}$/.test(callback)) {
    return ContentService.createTextOutput(callback + '(' + txt + ');').setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(txt).setMimeType(ContentService.MimeType.JSON);
}

// ---------------------------------------------------------------------- sesiones
function handleSession_(d) {
  if (findRow_('Sesiones', 1, d.session_id) > 0) return; // duplicado (reintento)
  var s = d.summary || {};
  var prices = priceMap_();
  ensurePrices_(s.tonnes_by_type || {}, s.type_names || {}, prices);
  var esName = esNames_();

  var value = 0, minerals = [];
  Object.keys(s.tonnes_by_type || {}).forEach(function (t) {
    var n = s.tonnes_by_type[t];
    value += n * (prices[t] || 0);
    minerals.push((esName[t] || t) + ' ' + n + 't');
  });
  var hours = (s.duration_s || 0) / 3600;
  var crh = hours > 0.02 ? Math.round(value / hours) : '';
  var mats = Object.keys(d.materials || {}).map(function (k) { return k + ' ' + d.materials[k]; }).join(', ');

  // Sitios: uno por grupo de plataformas del mismo mineral
  var siteIds = {};
  (s.sites || []).forEach(function (st) {
    var id = assignSite_(d, st, esName, prices);
    siteIds[st.idx] = id;
    sheet_('Visitas').appendRow([d.session_id, id, d.end, d.cmdr, esName[st.main_type] || st.main_type, st.rigs,
      nz_(st.rig_spacing_min_m), nz_(st.extent_m), st.collections, st.tonnes, nz_(st.tonnes_per_collection),
      s.terrain, nz_(s.eff_speed_median_ms)]);
  });
  var ids = Object.keys(siteIds).map(function (k) { return siteIds[k]; });

  sheet_('Sesiones').appendRow([
    d.session_id, ids.join(', '), new Date(), d.cmdr, d.system, d.body, d.start, d.end,
    round_((s.duration_s || 0) / 60, 1), s.rigs, s.collections, nz_(s.tonnes_per_collection),
    s.cycle_s_median ? round_(s.cycle_s_median / 60, 1) : '', nz_(d.site_signal), nz_(d.mining_locations_on_body),
    mats, (d.loads_to_ship || []).join(' + '), s.tonnes, Math.round(value), crh, nz_((s.route || {}).loop_m),
    nz_(s.eff_speed_median_ms), nz_(s.moving_speed_ms), nz_(s.sinuosity_median), s.terrain, s.track_len_m,
    minerals.join(', '), d.planet_class, d.gravity_g, d.temp_k, d.planet_radius_m, d.srv_type, d.close_reason,
    (d.unknown_events || []).join(', '), d.plugin_version
  ]);

  var pl = sheet_('Plataformas');
  (s.rig_list || []).forEach(function (r) {
    pl.appendRow([d.session_id, siteIds[r.site] || '', r.idx, r.lat, r.lon, esName[r.main_type] || r.main_type,
                  r.tonnes, r.collections, nz_(r.tonnes_per_collection),
                  new Date(r.first_t * 1000), new Date(r.last_t * 1000)]);
  });
  var tr = sheet_('Tramos');
  (s.segments || []).forEach(function (g) {
    tr.appendRow([d.session_id, g.from, g.to, g.straight_m, g.path_m, g.time_s, nz_(g.eff_speed_ms), nz_(g.sinuosity)]);
  });
  var track = d.track || '';
  var rc = sheet_('Recorridos');
  for (var i = 0, part = 1; i < track.length; i += TRACK_CHUNK, part++) {
    rc.appendRow([d.session_id, part, track.slice(i, i + TRACK_CHUNK)]);
  }
  if (d.body) handleBody_({ system: d.system, body: d.body, planet_class: d.planet_class, gravity_g: d.gravity_g,
                            temp_k: d.temp_k, radius_m: d.planet_radius_m, atmosphere: d.atmosphere,
                            mining_locations: d.mining_locations_on_body, cmdr: d.cmdr });
  ids.forEach(function (id) { recomputeSite_(id, prices); });
  recomputeNearest_(d.system, d.body, d.planet_radius_m);
}

function assignSite_(d, st, esName, prices) {
  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var values = sh.getDataRange().getValues();
  var R = d.planet_radius_m || 0;
  var best = null, bestD = null;
  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    if (row[1] !== d.system || row[2] !== d.body || row[4] !== st.main_type || !R) continue;
    var dist = haversine_(st.lat, st.lon, row[6], row[7], R);
    if (dist <= SITE_MATCH_M && (bestD === null || dist < bestD)) { best = row[0]; bestD = dist; }
  }
  if (best) return best;
  var id = 'S' + Utilities.formatString('%05d', values.length);
  var row = new Array(H.length).fill('');
  var set = function (n, v) { row[H.indexOf(n)] = (v === null || v === undefined) ? '' : v; };
  set('SiteID', id); set('Sistema', d.system); set('Cuerpo', d.body);
  set('Mineral', esName[st.main_type] || st.main_type); set('Nombre interno', st.main_type);
  set('Lat', st.lat); set('Lon', st.lon); set('Señal zona', d.site_signal);
  set('Sitios minería en cuerpo', d.mining_locations_on_body); set('Tipo planeta', d.planet_class);
  set('Gravedad (g)', d.gravity_g); set('Temp (K)', d.temp_k);
  sh.appendRow(row);
  return id;
}

function recomputeSite_(siteId, prices) {
  var vis = sheet_('Visitas').getDataRange().getValues();
  var VH = vis[0];
  var vc = function (n) { return VH.indexOf(n); };
  var rows = vis.slice(1).filter(function (r) { return r[1] === siteId; });
  if (!rows.length) return;
  var vals = function (n) { return rows.map(function (r) { return r[vc(n)]; }).filter(function (x) { return x !== '' && x !== null; }); };
  var median = function (v) {
    if (!v.length) return '';
    v = v.slice().sort(function (a, b) { return a - b; });
    var m = Math.floor(v.length / 2);
    return v.length % 2 ? v[m] : round_((v[m - 1] + v[m]) / 2, 2);
  };
  var sum = function (v) { return v.reduce(function (a, b) { return a + Number(b); }, 0); };

  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var r = findRow_('Sitios', 1, siteId);
  var cur = sh.getRange(r, 1, 1, H.length).getValues()[0];
  var set = function (n, v) { cur[H.indexOf(n)] = v; };
  var price = prices[String(cur[H.indexOf('Nombre interno')]).toLowerCase()] || 0;
  var maxRigs = Math.max.apply(null, vals('Plataformas').concat([0]));
  var spacing = vals('Dist. mín entre plataformas (m)');
  var tpc = median(vals('T/recogida'));
  var votes = {};
  vals('Terreno zona').forEach(function (t) { if (t !== 'sin datos') votes[t] = (votes[t] || 0) + 1; });

  set('Precio (Cr)', price);
  set('Máx plataformas', maxRigs);
  set('Dist. mín entre plataformas (m)', spacing.length ? Math.min.apply(null, spacing) : '');
  set('Extensión (m)', Math.max.apply(null, vals('Extensión (m)').concat([0])));
  set('T/recogida', tpc);
  // Valor de recoger todas las plataformas una vez: la cifra para comparar sitios
  set('Valor por vuelta (Cr)', tpc !== '' ? Math.round(maxRigs * tpc * price) : '');
  set('Visitas', rows.length);
  set('Recogidas', sum(vals('Recogidas')));
  set('Toneladas totales', sum(vals('Toneladas')));
  set('Terreno zona', Object.keys(votes).sort(function (a, b) { return votes[b] - votes[a]; })[0] || 'sin datos');
  set('Vel. efectiva zona (m/s)', median(vals('Vel. efectiva zona (m/s)')));
  set('Última visita', rows[rows.length - 1][vc('Fecha')]);
  set('Último CMDR', rows[rows.length - 1][vc('CMDR')]);
  sh.getRange(r, 1, 1, H.length).setValues([cur]);
}

// Distancia de cada sitio al más cercano del mismo cuerpo (datos de toda la flota)
function recomputeNearest_(system, body, R) {
  if (!R) return;
  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var values = sh.getDataRange().getValues();
  var idx = [];
  for (var i = 1; i < values.length; i++) if (values[i][1] === system && values[i][2] === body) idx.push(i);
  var cLat = H.indexOf('Lat'), cLon = H.indexOf('Lon'), cMin = H.indexOf('Nombre interno');
  idx.forEach(function (i) {
    var any = null, same = null;
    idx.forEach(function (j) {
      if (i === j) return;
      var dd = haversine_(values[i][cLat], values[i][cLon], values[j][cLat], values[j][cLon], R);
      if (any === null || dd < any) any = dd;
      if (values[i][cMin] === values[j][cMin] && (same === null || dd < same)) same = dd;
    });
    sh.getRange(i + 1, H.indexOf('Sitio más cercano (m)') + 1, 1, 2)
      .setValues([[any === null ? '' : Math.round(any), same === null ? '' : Math.round(same)]]);
  });
}

function esNames_() {
  var m = {};
  sheet_('Precios').getDataRange().getValues().slice(1).forEach(function (p) {
    if (p[0]) m[String(p[0]).toLowerCase()] = p[1] || p[0];
  });
  return m;
}

// ------------------------------------------------------------------------- otros
function handleSale_(d) {
  sheet_('Ventas').appendRow([d.time, d.cmdr, d.type, d.name, d.count, d.sell_price, d.total, d.system, d.market_id]);
}

function handleBody_(d) {
  var sh = sheet_('Cuerpos');
  var values = sh.getDataRange().getValues();
  var row = [d.system, d.body, d.planet_class || '', d.gravity_g || '', d.temp_k || '', d.radius_m || '',
             d.atmosphere || '', d.dist_ls || '', nz_(d.mining_locations), d.signals ? JSON.stringify(d.signals) : '',
             new Date(), d.cmdr || ''];
  for (var i = 1; i < values.length; i++) {
    if (values[i][0] === d.system && values[i][1] === d.body) {
      // no pisar datos buenos con vacíos
      for (var c = 0; c < row.length; c++) if (row[c] === '' || row[c] === null) row[c] = values[i][c];
      sh.getRange(i + 1, 1, 1, row.length).setValues([row]);
      return;
    }
  }
  sh.appendRow(row);
}

function handleEvent_(d) {
  sheet_('Eventos').appendRow([d.time, d.cmdr, d.event, d.system, d.body, d.lat, d.lon,
                               JSON.stringify(d.raw || {}).slice(0, 45000)]);
}

function priceMap_() {
  var v = sheet_('Precios').getDataRange().getValues().slice(1);
  var m = {};
  v.forEach(function (r) {
    var p = Number(r[3]) || 0;
    [r[0], r[1], r[2]].forEach(function (k) { if (k) m[String(k).toLowerCase()] = p; });
  });
  return m;
}

function ensurePrices_(tonnesByType, names, prices) {
  var sh = sheet_('Precios');
  Object.keys(tonnesByType).forEach(function (t) {
    var key = t.toLowerCase();
    var name = String(names[t] || '').toLowerCase();
    if (prices[key] === undefined && prices[name] !== undefined) {
      prices[key] = prices[name];
      // anotar el nombre interno real en la fila que coincide por nombre
      var v = sh.getDataRange().getValues();
      for (var i = 1; i < v.length; i++) {
        if (String(v[i][1]).toLowerCase() === name || String(v[i][2]).toLowerCase() === name) {
          sh.getRange(i + 1, 1).setValue(key);
          sh.getRange(i + 1, 5).setValue('sí');
          break;
        }
      }
    } else if (prices[key] === undefined) {
      sh.appendRow([key, names[t] || '', '', '', 'sí (nuevo, falta precio)']);
      prices[key] = 0;
    } else {
      var v2 = sh.getDataRange().getValues();
      for (var j = 1; j < v2.length; j++) {
        if (String(v2[j][0]).toLowerCase() === key && v2[j][4] !== 'sí') { sh.getRange(j + 1, 5).setValue('sí'); break; }
      }
    }
  });
}

// --------------------------------------------------------------------- utilidades
function sheet_(name) {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
  if (!sh) { setup(); sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name); }
  return sh;
}

function findRow_(name, col, value) {
  var v = sheet_(name).getRange(1, col, sheet_(name).getLastRow(), 1).getValues();
  for (var i = 1; i < v.length; i++) if (v[i][0] === value) return i + 1;
  return -1;
}

function haversine_(lat1, lon1, lat2, lon2, R) {
  var toR = Math.PI / 180;
  var dp = (lat2 - lat1) * toR, dl = (lon2 - lon1) * toR;
  var a = Math.pow(Math.sin(dp / 2), 2) + Math.cos(lat1 * toR) * Math.cos(lat2 * toR) * Math.pow(Math.sin(dl / 2), 2);
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

function round_(x, n) { var f = Math.pow(10, n); return Math.round(x * f) / f; }
function nz_(x) { return x === null || x === undefined ? '' : x; }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
