"use strict";

function crearAutocompletado({entrada, lista, url, contexto = () => "", alSeleccionar = () => {}}) {
    let sugerencias = [], activo = -1, temporizador, controlador;
    const cerrar = () => { activo = -1; lista.hidden = true; lista.replaceChildren(); entrada.setAttribute("aria-expanded", "false"); entrada.removeAttribute("aria-activedescendant"); };
    const seleccionar = indice => { const sugerencia = sugerencias[indice]; if (!sugerencia) return; entrada.value = sugerencia.valor; alSeleccionar(sugerencia); cerrar(); };
    const pintar = () => {
        lista.replaceChildren(...sugerencias.map((sugerencia, indice) => {
            const opcion = document.createElement("li"); opcion.id = `${lista.id}-opcion-${indice}`;
            opcion.setAttribute("role", "option"); opcion.setAttribute("aria-selected", String(indice === activo));
            opcion.textContent = sugerencia.etiqueta;
            opcion.addEventListener("mousedown", evento => { evento.preventDefault(); seleccionar(indice); });
            return opcion;
        }));
        lista.hidden = sugerencias.length === 0; entrada.setAttribute("aria-expanded", String(sugerencias.length > 0));
        if (activo >= 0) entrada.setAttribute("aria-activedescendant", `${lista.id}-opcion-${activo}`);
    };
    const consultar = async () => {
        const texto = entrada.value.trim(); if (texto.length < 2) return cerrar();
        if (controlador) controlador.abort(); controlador = new AbortController();
        try {
            const respuesta = await fetch(`${url}?q=${encodeURIComponent(texto)}${contexto()}`, {headers: {Accept: "application/json"}, signal: controlador.signal});
            if (!respuesta.ok) return cerrar();
            const datos = await respuesta.json();
            sugerencias = datos.municipios ? datos.municipios.map(item => ({valor: item.municipio, provincia: item.provincia || "", etiqueta: [item.municipio, item.provincia, item.comunidad_autonoma].filter(Boolean).join(" — ")})) : (datos.puestos || []).map(item => ({valor: item, etiqueta: item}));
            activo = -1; pintar();
        } catch (error) { if (error.name !== "AbortError") cerrar(); }
    };
    entrada.addEventListener("input", () => { alSeleccionar(null); clearTimeout(temporizador); temporizador = setTimeout(consultar, 250); });
    entrada.addEventListener("keydown", evento => {
        if (evento.key === "ArrowDown") { evento.preventDefault(); if (sugerencias.length) { activo = (activo + 1) % sugerencias.length; pintar(); } }
        else if (evento.key === "ArrowUp") { evento.preventDefault(); if (sugerencias.length) { activo = (activo - 1 + sugerencias.length) % sugerencias.length; pintar(); } }
        else if (evento.key === "Enter" && activo >= 0) { evento.preventDefault(); seleccionar(activo); }
        else if (evento.key === "Escape") cerrar();
    });
    entrada.addEventListener("blur", () => setTimeout(cerrar, 150));
}

document.addEventListener("DOMContentLoaded", () => {
    const comunidad = document.querySelector("#comunidad_autonoma"), provincia = document.querySelector("#provincia");
    const municipio = document.querySelector("#municipio"), municipioExacto = document.querySelector("#municipio_exacto"), municipioProvinciaExacto = document.querySelector("#municipio_provincia_exacto");
    if (municipio && municipioExacto && municipioProvinciaExacto) crearAutocompletado({entrada: municipio, lista: document.querySelector("#sugerencias-municipio"), url: "/api/filtros/municipios", contexto: () => `&comunidad=${encodeURIComponent(comunidad.value)}&provincia=${encodeURIComponent(provincia.value)}`, alSeleccionar: sugerencia => { municipioExacto.value = sugerencia ? sugerencia.valor : ""; municipioProvinciaExacto.value = sugerencia ? sugerencia.provincia : ""; }});
    const puesto = document.querySelector("#texto");
    if (puesto) crearAutocompletado({entrada: puesto, lista: document.querySelector("#sugerencias-puesto"), url: "/api/filtros/puestos"});
    const formulario = document.querySelector(".search-form"), estado = document.querySelector("#estado-actualizacion");
    const botonBuscar = formulario?.querySelector('button[type="submit"]');
    const mensajeEstado = () => document.querySelector("#estado-actualizacion-mensaje");
    const detalleEstado = () => document.querySelector("#estado-actualizacion-detalle");
    const barraEstado = () => document.querySelector("#estado-actualizacion-barra");
    const mostrarEstado = (mensaje, detalle = "", porcentaje = 0) => {
        estado.hidden = false; mensajeEstado().textContent = mensaje; detalleEstado().textContent = detalle;
        barraEstado().style.width = `${porcentaje}%`;
    };
    const restaurarFormulario = () => { if (botonBuscar) botonBuscar.disabled = false; };
    const mostrarError = error => { mostrarEstado(error, "Puedes volver a intentarlo."); restaurarFormulario(); };
    const iniciarActualizacion = async () => {
        const datos = new FormData(formulario);
        if (botonBuscar) botonBuscar.disabled = true;
        try {
            const respuesta = await fetch("/api/actualizar-busqueda", {method: "POST", headers: {"Content-Type": "application/json", Accept: "application/json"}, body: JSON.stringify({fecha_desde: datos.get("fecha_desde"), fecha_hasta: datos.get("fecha_hasta")})});
            const resultado = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error(resultado.error || "No se pudo comprobar la cobertura.");
            if (!resultado.actualizacion) return navegarResultados(datos);
            if (!resultado.trabajo?.id) throw new Error("La actualización no devolvió un trabajo válido.");
            vigilarTrabajo(resultado.trabajo.id, datos);
        } catch (error) { mostrarError(error.message || "No se pudo comprobar la cobertura."); }
    };
    const formatearDuracion = segundos => {
        if (!Number.isFinite(segundos)) return "calculando…";
        const minutos = Math.floor(segundos / 60), resto = Math.round(segundos % 60);
        return minutos ? `${minutos} min ${resto} s` : `${resto} s`;
    };
    const navegarResultados = (datos, conError = false) => {
        const parametros = new URLSearchParams(datos);
        if (conError) parametros.set("actualizacion", "error");
        window.location.assign(`${formulario.action}?${parametros.toString()}#resultados`);
    };
    const vigilarTrabajo = async (id, datos) => {
        BOEActualizacion.vigilarTrabajo(id, {
            alProgreso: (trabajo, formatear) => {
                const porcentaje = Number.isFinite(trabajo.porcentaje) ? trabajo.porcentaje : 0;
                const restante = trabajo.restante_estimado_segundos === null ? "Tiempo restante: calculando…" : `Restante aprox.: ${formatear(trabajo.restante_estimado_segundos)}`;
                mostrarEstado(trabajo.mensaje || "Actualizando datos del BOE…", `${porcentaje} % · Transcurrido: ${formatear(trabajo.transcurrido_segundos)} · ${restante}`, porcentaje);
            },
            alCompletar: () => { mostrarEstado("Actualización completada", "100 %", 100); window.setTimeout(() => navegarResultados(datos), 250); },
            alError: () => navegarResultados(datos, true),
        });
    };
    if (formulario && estado) {
        formulario.addEventListener("submit", evento => {
            const datos = new FormData(formulario);
            if (!datos.get("fecha_desde")) return;
            evento.preventDefault(); iniciarActualizacion();
        });
        if (estado.dataset.requiereActualizacion === "true") iniciarActualizacion();
    }
    if (window.location.hash === "#resultados") document.querySelector("#resultados")?.scrollIntoView({block: "start"});
});
