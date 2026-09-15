"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const raiz = document.querySelector(".cobertura"); if (!raiz) return;
    const estado = document.querySelector("#estado-actualizacion"), boton = document.querySelector("#actualizar-pendientes");
    const mensaje = document.querySelector("#mensaje-cobertura"), detalle = document.querySelector("#detalle-cobertura");
    const fechasActualizadas = new Set();
    const mostrar = (texto, detalleTexto = "", porcentaje = 0) => { estado.hidden = false; document.querySelector("#estado-actualizacion-mensaje").textContent = texto; document.querySelector("#estado-actualizacion-detalle").textContent = detalleTexto; document.querySelector("#estado-actualizacion-barra").style.width = `${porcentaje}%`; };
    const restaurar = () => { boton.disabled = false; };
    const crearElemento = (etiqueta, texto) => {
        const elemento = document.createElement(etiqueta);
        elemento.textContent = texto;
        return elemento;
    };
    const anadirDetalle = (lista, etiqueta, valor) => {
        lista.append(crearElemento("dt", etiqueta), crearElemento("dd", valor));
    };
    const mostrarDetalle = dato => {
        const titulo = crearElemento("h2", dato.fecha);
        const lista = document.createElement("dl");
        anadirDetalle(lista, "Estado almacenado", dato.estado || "—");
        anadirDetalle(lista, "Estado calculado", dato.estado_visual.replaceAll("_", " "));
        anadirDetalle(lista, "Cubierto", dato.cubierto ? "Sí" : "No");
        anadirDetalle(lista, "Versión extractor", dato.version_extractor || "—");
        anadirDetalle(lista, "Última consulta", dato.fecha_ultima_consulta || "—");
        anadirDetalle(lista, "Publicaciones según BOE", dato.numero_publicaciones ?? "—");
        anadirDetalle(lista, "Publicaciones conservadas en SQLite", dato.publicaciones_sqlite ?? "—");
        if (dato.motivo) anadirDetalle(lista, "Motivo", dato.motivo);
        detalle.replaceChildren(titulo, lista);
    };
    const mostrarErrorDetalle = texto => detalle.replaceChildren(
        crearElemento("h2", "Detalle diario"), crearElemento("p", texto)
    );
    const refrescarFecha = async fecha => {
        const respuesta = await fetch(`/api/cobertura/dia?fecha=${encodeURIComponent(fecha)}`);
        const dato = await respuesta.json();
        if (!respuesta.ok) throw new Error(dato.error || "No se pudo actualizar el día.");
        const dia = raiz.querySelector(`[data-fecha="${CSS.escape(fecha)}"]`);
        if (dia) {
            dia.className = `coverage-day coverage-day--${String(dato.estado_visual || "pendiente").toLowerCase()}`;
            dia.querySelector("span").textContent = String(dato.estado_visual || "pendiente").replaceAll("_", " ");
        }
    };
    document.querySelectorAll(".coverage-day").forEach(dia => dia.addEventListener("click", async () => {
        try {
            const respuesta = await fetch(`/api/cobertura/dia?fecha=${encodeURIComponent(dia.dataset.fecha)}`); const dato = await respuesta.json();
            if (!respuesta.ok) throw new Error(dato.error || "No se pudo obtener el detalle.");
            mostrarDetalle(dato);
        } catch (error) { mostrarErrorDetalle(error.message); }
    }));
    boton.addEventListener("click", async () => {
        boton.disabled = true; mensaje.textContent = "";
        try {
            const respuesta = await fetch("/api/cobertura/actualizar", {method: "POST", headers: {"Content-Type": "application/json", Accept: "application/json"}, body: JSON.stringify({anio: Number(raiz.dataset.anio), mes: Number(raiz.dataset.mes)})});
            const resultado = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error(resultado.error || "No se pudo comprobar la cobertura.");
            if (!resultado.actualizacion) { mensaje.textContent = "El periodo seleccionado ya está cubierto."; restaurar(); return; }
            BOEActualizacion.vigilarTrabajo(resultado.trabajo.id, {
                alProgreso: (trabajo, formatear) => { const restante = trabajo.restante_estimado_segundos === null ? "Tiempo restante: calculando…" : `Restante aprox.: ${formatear(trabajo.restante_estimado_segundos)}`; mostrar(trabajo.mensaje, `${trabajo.porcentaje} % · Transcurrido: ${formatear(trabajo.transcurrido_segundos)} · ${restante}`, trabajo.porcentaje); (trabajo.fechas_completadas || []).forEach(item => { const fecha = typeof item === "string" ? item : item.fecha; if (!fecha || fechasActualizadas.has(fecha)) return; fechasActualizadas.add(fecha); refrescarFecha(fecha).catch(() => {}); }); },
                alCompletar: () => { mostrar("Actualización completada", "100 %", 100); window.setTimeout(() => window.location.reload(), 250); },
                alError: texto => { mostrar(texto, "Puedes volver a intentarlo."); restaurar(); },
            });
        } catch (error) { mensaje.textContent = error.message || "No se pudo comprobar la cobertura."; restaurar(); }
    });
});
