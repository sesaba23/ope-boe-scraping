"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const raiz = document.querySelector(".cobertura"); if (!raiz) return;
    const estado = document.querySelector("#estado-actualizacion"), boton = document.querySelector("#actualizar-pendientes");
    const mensaje = document.querySelector("#mensaje-cobertura"), detalle = document.querySelector("#detalle-cobertura");
    const mostrar = (texto, detalleTexto = "", porcentaje = 0) => { estado.hidden = false; document.querySelector("#estado-actualizacion-mensaje").textContent = texto; document.querySelector("#estado-actualizacion-detalle").textContent = detalleTexto; document.querySelector("#estado-actualizacion-barra").style.width = `${porcentaje}%`; };
    const restaurar = () => { boton.disabled = false; };
    document.querySelectorAll(".coverage-day").forEach(dia => dia.addEventListener("click", async () => {
        try {
            const respuesta = await fetch(`/api/cobertura/dia?fecha=${encodeURIComponent(dia.dataset.fecha)}`); const dato = await respuesta.json();
            if (!respuesta.ok) throw new Error(dato.error || "No se pudo obtener el detalle.");
            detalle.innerHTML = `<h2>${dato.fecha}</h2><dl><dt>Estado almacenado</dt><dd>${dato.estado || "—"}</dd><dt>Estado calculado</dt><dd>${dato.estado_visual.replaceAll("_", " ")}</dd><dt>Cubierto</dt><dd>${dato.cubierto ? "Sí" : "No"}</dd><dt>Versión extractor</dt><dd>${dato.version_extractor || "—"}</dd><dt>Última consulta</dt><dd>${dato.fecha_ultima_consulta || "—"}</dd><dt>Publicaciones según BOE</dt><dd>${dato.numero_publicaciones ?? "—"}</dd><dt>Publicaciones conservadas en SQLite</dt><dd>${dato.publicaciones_sqlite ?? "—"}</dd>${dato.motivo ? `<dt>Motivo</dt><dd>${dato.motivo}</dd>` : ""}</dl>`;
        } catch (error) { detalle.innerHTML = `<h2>Detalle diario</h2><p>${error.message}</p>`; }
    }));
    boton.addEventListener("click", async () => {
        boton.disabled = true; mensaje.textContent = "";
        try {
            const respuesta = await fetch("/api/cobertura/actualizar", {method: "POST", headers: {"Content-Type": "application/json", Accept: "application/json"}, body: JSON.stringify({anio: Number(raiz.dataset.anio), mes: Number(raiz.dataset.mes)})});
            const resultado = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error(resultado.error || "No se pudo comprobar la cobertura.");
            if (!resultado.actualizacion) { mensaje.textContent = "El periodo seleccionado ya está cubierto."; restaurar(); return; }
            BOEActualizacion.vigilarTrabajo(resultado.trabajo.id, {
                alProgreso: (trabajo, formatear) => { const restante = trabajo.restante_estimado_segundos === null ? "Tiempo restante: calculando…" : `Restante aprox.: ${formatear(trabajo.restante_estimado_segundos)}`; mostrar(trabajo.mensaje, `${trabajo.porcentaje} % · Transcurrido: ${formatear(trabajo.transcurrido_segundos)} · ${restante}`, trabajo.porcentaje); },
                alCompletar: () => { mostrar("Actualización completada", "100 %", 100); window.setTimeout(() => window.location.reload(), 250); },
                alError: texto => { mostrar(texto, "Puedes volver a intentarlo."); restaurar(); },
            });
        } catch (error) { mensaje.textContent = error.message || "No se pudo comprobar la cobertura."; restaurar(); }
    });
});
