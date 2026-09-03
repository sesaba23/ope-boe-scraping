"use strict";

window.BOEActualizacion = (() => {
    const formatearDuracion = segundos => {
        if (!Number.isFinite(segundos)) return "calculando…";
        const minutos = Math.floor(segundos / 60), resto = Math.round(segundos % 60);
        return minutos ? `${minutos} min ${resto} s` : `${resto} s`;
    };
    const vigilarTrabajo = async (id, {alProgreso, alCompletar, alError}) => {
        const revisar = async () => {
            try {
                const respuesta = await fetch(`/api/trabajos/${encodeURIComponent(id)}`, {headers: {Accept: "application/json"}});
                const trabajo = await respuesta.json().catch(() => ({}));
                if (!respuesta.ok || trabajo.estado === "error") return alError(trabajo.error || "No se pudo completar la actualización del BOE.");
                alProgreso(trabajo, formatearDuracion);
                if (trabajo.estado === "completado") return alCompletar(trabajo);
                window.setTimeout(revisar, 700);
            } catch (_) { alError("No se pudo consultar el estado de la actualización."); }
        };
        revisar();
    };
    return {formatearDuracion, vigilarTrabajo};
})();
