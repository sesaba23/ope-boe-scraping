"use strict";

const botonMenu = document.querySelector(".site-menu-button");
const navegacion = document.querySelector("#site-navigation");

if (botonMenu && navegacion) {
    botonMenu.addEventListener("click", () => {
        const abierto = botonMenu.getAttribute("aria-expanded") === "true";
        botonMenu.setAttribute("aria-expanded", String(!abierto));
        navegacion.classList.toggle("is-open", !abierto);
    });
}
