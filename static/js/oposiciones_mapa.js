"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const pestanas = [...document.querySelectorAll("[data-results-tab]")];
    const paneles = [...document.querySelectorAll("[data-results-panel]")];
    const contenedor = document.querySelector("#mapa-oposiciones");
    if (!pestanas.length || !contenedor) return;

    const cargando = document.querySelector("#mapa-cargando");
    const error = document.querySelector("#mapa-error");
    const resumen = document.querySelector("#mapa-resumen");
    const sinResultados = document.querySelector("#mapa-sin-resultados");
    const botonSinCoordenadas = document.querySelector("#mapa-sin-coordenadas");
    const panelSinCoordenadas = document.querySelector("#panel-sin-coordenadas");
    const totalSinCoordenadas = document.querySelector("#sin-coordenadas-total");
    const cargaSinCoordenadas = document.querySelector("#sin-coordenadas-cargando");
    const errorSinCoordenadas = document.querySelector("#sin-coordenadas-error");
    const vacioSinCoordenadas = document.querySelector("#sin-coordenadas-vacio");
    const resultadosSinCoordenadas = document.querySelector("#sin-coordenadas-resultados");
    const paginacionSinCoordenadas = document.querySelector("#sin-coordenadas-paginacion");
    const paginaSinCoordenadas = document.querySelector("#sin-coordenadas-pagina");
    const anteriorSinCoordenadas = document.querySelector("#sin-coordenadas-anterior");
    const siguienteSinCoordenadas = document.querySelector("#sin-coordenadas-siguiente");
    const panelPlazo = document.querySelector("#panel-plazo-abierto");
    const cargandoPlazos = document.querySelector("#plazo-abierto-cargando");
    const errorPlazos = document.querySelector("#plazo-abierto-error");
    const resumenPlazos = document.querySelector("#plazo-abierto-resumen");
    const listadoPlazos = document.querySelector("#plazo-abierto-listado");
    const paginacionPlazos = document.querySelector("#plazo-abierto-paginacion");
    const paginaPlazos = document.querySelector("#plazo-abierto-pagina");
    const anteriorPlazos = document.querySelector("#plazo-abierto-anterior");
    const siguientePlazos = document.querySelector("#plazo-abierto-siguiente");
    const formatoNumero = new Intl.NumberFormat("es-ES");
    const formatoFecha = new Intl.DateTimeFormat("es-ES", {day: "numeric", month: "long", year: "numeric"});
    const cacheSinCoordenadas = new Map();
    const cachePlazos = new Map();
    let mapa, capaMunicipios, mapaCargado = false, paginaActualSinCoordenadas = 1, paginaActualPlazos = 1;

    const mostrarPanel = nombre => {
        pestanas.forEach(pestana => {
            const activo = pestana.dataset.resultsTab === nombre;
            pestana.setAttribute("aria-selected", String(activo));
            pestana.classList.toggle("is-active", activo);
            pestana.tabIndex = activo ? 0 : -1;
        });
        paneles.forEach(panel => { panel.hidden = panel.dataset.resultsPanel !== nombre; });
    };
    const mostrarCarga = visible => { cargando.hidden = !visible; };
    const mostrarError = mensaje => {
        error.textContent = mensaje;
        error.hidden = false;
    };
    const limpiarEstado = () => {
        error.hidden = true;
        sinResultados.hidden = true;
    };
    const parametrosFiltros = () => {
        const permitidos = new Set([
            "texto", "fecha_desde", "fecha_hasta", "comunidad_autonoma", "provincia",
            "municipio", "municipio_exacto", "municipio_provincia_exacto", "administracion",
            "ambito", "tipo_entidad", "sistema", "turno", "escala", "subescala", "clase",
            "tipo_personal", "plazo",
        ]);
        const actuales = new URLSearchParams(window.location.search);
        const filtros = new URLSearchParams();
        actuales.forEach((valor, clave) => { if (permitidos.has(clave)) filtros.append(clave, valor); });
        return filtros;
    };
    const urlApi = (ruta, parametros) => {
        const consulta = parametros.toString();
        return ruta + (consulta ? "?" + consulta : "");
    };
    const parametrosRetorno = () => {
        const parametros = parametrosFiltros();
        const actuales = new URLSearchParams(window.location.search);
        ["pagina", "tamano_pagina", "orden", "ver_todas"].forEach(nombre => {
            if (actuales.has(nombre)) parametros.set(nombre, actuales.get(nombre));
        });
        parametros.set("vista", "mapa");
        parametros.set("sin_coordenadas", "1");
        parametros.set("pagina_sin_coordenadas", String(paginaActualSinCoordenadas));
        return parametros;
    };
    const desplazarPanelSinCoordenadas = () => {
        const reducirMovimiento = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        panelSinCoordenadas.scrollIntoView({behavior: reducirMovimiento ? "auto" : "smooth", block: "start"});
    };
    const textoUbicacion = municipio => [
        municipio.provincia,
        municipio.comunidad_autonoma,
    ].filter(Boolean).join(" · ");
    const contenidoPopup = municipio => {
        const contenido = document.createElement("div");
        const titulo = document.createElement("strong");
        titulo.textContent = municipio.municipio;
        contenido.append(titulo);
        const ubicacion = textoUbicacion(municipio);
        if (ubicacion) {
            const lugar = document.createElement("div");
            lugar.textContent = ubicacion;
            contenido.append(lugar);
        }
        const convocatorias = document.createElement("div");
        convocatorias.textContent = formatoNumero.format(municipio.convocatorias) + " convocatorias";
        contenido.append(convocatorias);
        const plazas = document.createElement("div");
        plazas.textContent = formatoNumero.format(municipio.plazas) + " plazas";
        contenido.append(plazas);
        return contenido;
    };
    const prepararMapa = () => {
        if (mapa) return;
        if (!window.L) throw new Error("No se pudo cargar el mapa. Vuelve a intentarlo.");
        mapa = window.L.map(contenedor).setView([40.1, -3.6], 5);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap contributors",
            maxZoom: 18,
        }).addTo(mapa);
    };
    const pintarResumen = datos => {
        const datosResumen = datos.resumen;
        resumen.textContent = [
            formatoNumero.format(datosResumen.convocatorias) + " convocatorias",
            formatoNumero.format(datosResumen.plazas) + " plazas",
            formatoNumero.format(datosResumen.municipios) + " municipios",
            formatoNumero.format(datosResumen.geolocalizadas) + " geolocalizadas",
        ].join(" · ");
        resumen.hidden = false;
        const sinCoordenadas = Number(datosResumen.sin_coordenadas);
        botonSinCoordenadas.hidden = sinCoordenadas <= 0;
        botonSinCoordenadas.textContent = "Sin coordenadas: " + formatoNumero.format(sinCoordenadas);
    };
    const pintarMunicipios = datos => {
        prepararMapa();
        if (capaMunicipios) mapa.removeLayer(capaMunicipios);
        capaMunicipios = window.L.markerClusterGroup
            ? window.L.markerClusterGroup()
            : window.L.layerGroup();
        const marcadores = datos.municipios.map(municipio => {
            const marcador = window.L.marker([municipio.latitud, municipio.longitud]);
            marcador.bindPopup(contenidoPopup(municipio));
            capaMunicipios.addLayer(marcador);
            return marcador;
        });
        capaMunicipios.addTo(mapa);
        if (!marcadores.length) {
            sinResultados.hidden = false;
            return;
        }
        const limites = window.L.featureGroup(marcadores).getBounds();
        if (marcadores.length === 1) mapa.setView(limites.getCenter(), 12);
        else mapa.fitBounds(limites, {padding: [24, 24]});
    };
    const fechaDesdeIso = iso => new Date(`${iso}T00:00:00`);
    const fechaLegible = iso => {
        const texto = formatoFecha.format(fechaDesdeIso(iso));
        return texto.charAt(0).toUpperCase() + texto.slice(1);
    };
    const diasHasta = (fecha, referencia) => Math.round(
        (fechaDesdeIso(fecha) - fechaDesdeIso(referencia)) / 86400000
    );
    const urgenciaPlazo = dias => dias <= 1 ? "urgente" : dias <= 3 ? "proximo" : dias <= 14 ? "cercano" : "abierto";
    const textoVencimiento = dias => dias <= 0 ? "Vence hoy" : dias === 1 ? "Vence mañana" : `Vence en ${dias} días`;
    const pintarPlazos = datos => {
        listadoPlazos.replaceChildren();
        const grupos = new Map();
        datos.filas.forEach(fila => {
            if (!grupos.has(fila.fecha_fin_plazo)) grupos.set(fila.fecha_fin_plazo, []);
            grupos.get(fila.fecha_fin_plazo).push(fila);
        });
        const proximo = datos.filas[0]?.fecha_fin_plazo;
        resumenPlazos.textContent = `${formatoNumero.format(datos.total)} convocatorias en plazo · Próximo vencimiento: ${proximo ? fechaLegible(proximo) : "—"}`;
        const volver = urlApi("/oposiciones", parametrosFiltros());
        grupos.forEach((filas, fecha) => {
            const dias = diasHasta(fecha, datos.fecha_referencia);
            const grupo = document.createElement("section");
            grupo.className = `open-deadlines-group open-deadlines-group--${urgenciaPlazo(dias)}`;
            const encabezado = document.createElement("header");
            encabezado.className = "open-deadlines-group-heading";
            const titulo = document.createElement("h3");
            titulo.textContent = fechaLegible(fecha);
            const contador = document.createElement("span");
            contador.className = "open-deadlines-count";
            contador.textContent = `${filas.length} ${filas.length === 1 ? "convocatoria" : "convocatorias"}`;
            encabezado.append(titulo, contador);
            const urgencia = document.createElement("p");
            urgencia.className = "open-deadlines-urgency";
            urgencia.textContent = textoVencimiento(dias);
            encabezado.append(urgencia);
            grupo.append(encabezado);
            const lista = document.createElement("div");
            lista.className = "open-deadlines-items";
            filas.forEach(fila => {
                const tarjeta = document.createElement("article");
                tarjeta.className = "open-deadline-card";
                const cabecera = document.createElement("div");
                cabecera.className = "open-deadline-card-heading";
                const puesto = document.createElement("h4");
                puesto.textContent = fila.puesto_normalizado || fila.puesto || "Puesto no disponible";
                cabecera.append(puesto);
                const enlace = document.createElement("a");
                enlace.className = "portal-button portal-button--small";
                enlace.href = `/oposiciones/${encodeURIComponent(String(fila.oposicion_id))}?volver=${encodeURIComponent(volver)}`;
                enlace.textContent = "Ver detalle";
                cabecera.append(enlace);
                tarjeta.append(cabecera);
                const meta = document.createElement("div");
                meta.className = "open-deadline-card-meta";
                [
                    ["Plazas", fila.num_plazas === null ? null : formatoNumero.format(fila.num_plazas)],
                    ["Administración", fila.administracion],
                    ["Ubicación", [fila.municipio, fila.provincia, fila.comunidad_autonoma].filter(Boolean).join(" · ")],
                    ["Tipo de personal", fila.tipo_personal || "Otros"],
                    ["Plazo", fila.plazo_solicitudes],
                ].forEach(([etiqueta, valor]) => {
                    if (!valor) return;
                    const dato = document.createElement("span");
                    dato.textContent = `${etiqueta}: ${valor}`;
                    meta.append(dato);
                });
                tarjeta.append(meta);
                lista.append(tarjeta);
            });
            grupo.append(lista);
            listadoPlazos.append(grupo);
        });
        paginacionPlazos.hidden = datos.total_paginas <= 1;
        paginaPlazos.textContent = datos.total_paginas ? `Página ${datos.pagina} de ${datos.total_paginas}` : "";
        anteriorPlazos.disabled = datos.pagina <= 1;
        siguientePlazos.disabled = datos.pagina >= datos.total_paginas;
    };
    const mostrarCargaPlazos = visible => { cargandoPlazos.hidden = !visible; };
    const cargarPlazos = async pagina => {
        if (!panelPlazo) return;
        paginaActualPlazos = pagina;
        errorPlazos.hidden = true;
        if (cachePlazos.has(pagina)) {
            pintarPlazos(cachePlazos.get(pagina));
            return;
        }
        mostrarCargaPlazos(true);
        try {
            const parametros = parametrosFiltros();
            parametros.set("pagina", String(pagina));
            parametros.set("tamano", "30");
            const respuesta = await fetch(urlApi("/api/oposiciones/plazos-abiertos", parametros), {
                headers: {Accept: "application/json"},
            });
            const datos = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error(datos.error || "No se pudieron cargar los plazos abiertos.");
            cachePlazos.set(pagina, datos);
            pintarPlazos(datos);
        } catch (error) {
            errorPlazos.textContent = error.message || "No se pudieron cargar los plazos abiertos.";
            errorPlazos.hidden = false;
        } finally {
            mostrarCargaPlazos(false);
        }
    };
    const motivoLegible = motivo => ({
        sin_codigo_ine: "Municipio no identificado",
        codigo_ine_no_resuelto: "Código municipal no reconocido",
        municipio_sin_coordenadas: "Municipio sin coordenadas",
    })[motivo] || "Localización no disponible";
    const linea = (etiqueta, valor) => {
        if (!valor) return null;
        const elemento = document.createElement("span");
        elemento.textContent = etiqueta + ": " + valor;
        return elemento;
    };
    const pintarResultadosSinCoordenadas = datos => {
        resultadosSinCoordenadas.replaceChildren();
        totalSinCoordenadas.textContent = formatoNumero.format(datos.total) + " convocatorias";
        vacioSinCoordenadas.hidden = datos.total !== 0;
        datos.resultados.forEach(resultado => {
            const tarjeta = document.createElement("article");
            tarjeta.className = "without-coordinates-result";
            const cabecera = document.createElement("div");
            const puesto = document.createElement("strong");
            puesto.textContent = resultado.puesto || "Puesto no disponible";
            cabecera.append(puesto);
            if (Number.isInteger(Number(resultado.oposicion_id))) {
                const enlace = document.createElement("a");
                enlace.className = "portal-button portal-button--small";
                const volver = urlApi("/oposiciones", parametrosRetorno());
                enlace.href = "/oposiciones/" + encodeURIComponent(String(resultado.oposicion_id))
                    + "?volver=" + encodeURIComponent(volver);
                enlace.textContent = "Ver detalle";
                cabecera.append(enlace);
            }
            tarjeta.append(cabecera);
            const datosTarjeta = document.createElement("div");
            datosTarjeta.className = "without-coordinates-meta";
            [
                linea("Fecha BOE", resultado.fecha_boe),
                linea("Plazas", resultado.num_plazas === null ? null : formatoNumero.format(resultado.num_plazas)),
                linea("Administración", resultado.administracion),
                linea("Comunidad autónoma", resultado.comunidad_autonoma),
                linea("Provincia", resultado.provincia),
                linea("Municipio", resultado.municipio),
                linea("Motivo", motivoLegible(resultado.motivo_sin_coordenadas)),
            ].filter(Boolean).forEach(elemento => datosTarjeta.append(elemento));
            tarjeta.append(datosTarjeta);
            resultadosSinCoordenadas.append(tarjeta);
        });
        paginacionSinCoordenadas.hidden = datos.paginas === 0;
        paginaSinCoordenadas.textContent = datos.paginas ? "Página " + datos.pagina + " de " + datos.paginas : "";
        anteriorSinCoordenadas.disabled = datos.pagina <= 1;
        siguienteSinCoordenadas.disabled = datos.pagina >= datos.paginas;
    };
    const mostrarCargaSinCoordenadas = visible => { cargaSinCoordenadas.hidden = !visible; };
    const cargarSinCoordenadas = async pagina => {
        paginaActualSinCoordenadas = pagina;
        errorSinCoordenadas.hidden = true;
        if (cacheSinCoordenadas.has(pagina)) {
            pintarResultadosSinCoordenadas(cacheSinCoordenadas.get(pagina));
            return;
        }
        mostrarCargaSinCoordenadas(true);
        try {
            const parametros = parametrosFiltros();
            parametros.set("pagina", String(pagina));
            parametros.set("tamano", "50");
            const respuesta = await fetch(urlApi("/api/oposiciones/sin-coordenadas", parametros), {
                headers: {Accept: "application/json"},
            });
            const datos = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error("No se pudieron cargar las convocatorias sin coordenadas.");
            cacheSinCoordenadas.set(pagina, datos);
            pintarResultadosSinCoordenadas(datos);
        } catch (_error) {
            errorSinCoordenadas.hidden = false;
        } finally {
            mostrarCargaSinCoordenadas(false);
        }
    };
    const abrirSinCoordenadas = pagina => {
        panelSinCoordenadas.hidden = false;
        desplazarPanelSinCoordenadas();
        cargarSinCoordenadas(pagina);
    };
    const cargarMapa = async () => {
        if (mapaCargado) {
            window.requestAnimationFrame(() => mapa?.invalidateSize());
            return;
        }
        limpiarEstado();
        mostrarCarga(true);
        try {
            const respuesta = await fetch(urlApi("/api/oposiciones/mapa", parametrosFiltros()), {
                headers: {Accept: "application/json"},
            });
            const datos = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error(datos.error || "No se pudo cargar el mapa.");
            pintarResumen(datos);
            pintarMunicipios(datos);
            mapaCargado = true;
            window.requestAnimationFrame(() => mapa.invalidateSize());
        } catch (_error) {
            mostrarError("No se pudo cargar el mapa. Puedes volver al listado e intentarlo de nuevo.");
        } finally {
            mostrarCarga(false);
        }
    };
    const activarMapa = () => {
        mostrarPanel("mapa");
        cargarMapa();
    };
    const activarPlazos = () => {
        mostrarPanel("plazo-abierto");
        cargarPlazos(paginaActualPlazos);
    };

    pestanas.forEach((pestana, indice) => {
        pestana.addEventListener("click", () => {
            if (pestana.dataset.resultsTab === "mapa") activarMapa();
            else if (pestana.dataset.resultsTab === "plazo-abierto") activarPlazos();
            else mostrarPanel("listado");
        });
        pestana.addEventListener("keydown", evento => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(evento.key)) return;
            evento.preventDefault();
            const destino = evento.key === "Home" ? 0 : evento.key === "End" ? pestanas.length - 1
                : (indice + (evento.key === "ArrowRight" ? 1 : -1) + pestanas.length) % pestanas.length;
            pestanas[destino].focus();
            pestanas[destino].click();
        });
    });
    botonSinCoordenadas.addEventListener("click", () => abrirSinCoordenadas(paginaActualSinCoordenadas));
    document.querySelector("#sin-coordenadas-cerrar").addEventListener("click", () => { panelSinCoordenadas.hidden = true; });
    document.querySelector("#sin-coordenadas-reintentar").addEventListener("click", () => {
        cacheSinCoordenadas.delete(paginaActualSinCoordenadas);
        abrirSinCoordenadas(paginaActualSinCoordenadas);
    });
    anteriorSinCoordenadas.addEventListener("click", () => cargarSinCoordenadas(paginaActualSinCoordenadas - 1));
    siguienteSinCoordenadas.addEventListener("click", () => cargarSinCoordenadas(paginaActualSinCoordenadas + 1));
    if (panelPlazo) {
        anteriorPlazos.addEventListener("click", () => cargarPlazos(paginaActualPlazos - 1));
        siguientePlazos.addEventListener("click", () => cargarPlazos(paginaActualPlazos + 1));
    }
    const estadoVisual = new URLSearchParams(window.location.search);
    if (estadoVisual.get("vista") === "mapa") {
        document.querySelector('[data-results-tab="mapa"]').focus();
        activarMapa();
        if (estadoVisual.get("sin_coordenadas") === "1") {
            const paginaRestaurada = Number.parseInt(estadoVisual.get("pagina_sin_coordenadas"), 10);
            abrirSinCoordenadas(Number.isInteger(paginaRestaurada) && paginaRestaurada > 0 ? paginaRestaurada : 1);
        }
    }
});
