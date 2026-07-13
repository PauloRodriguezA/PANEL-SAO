#!/usr/bin/env python3
"""
EPA Entel - Encuesta Post Atencion.

Ejecutar local:
    python EPA.PY

Variables opcionales:
    EPA_HOST=127.0.0.1
    EPA_PORT=8081
    EPA_DB=C:\\ruta\\epa_entel_sao.sqlite3
    EPA_ADMIN_TOKEN=clave-privada

Flujo:
    1. Entrar a /admin y crear una atencion a evaluar.
    2. El sistema genera un link unico: /encuesta/entel/<token>
    3. El cliente responde sin ver los datos internos.
    4. El panel y exportaciones quedan asociados internamente a cliente, ST y tecnico.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import os
import secrets
import sqlite3
import sys
import traceback
import urllib.parse
import uuid
import zipfile
import xml.etree.ElementTree as ET
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("EPA_DB", APP_DIR / "epa_entel_sao.sqlite3"))
DEFAULT_HOST = os.environ.get("EPA_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("EPA_PORT") or os.environ.get("PORT") or "8081")
ADMIN_TOKEN = os.environ.get("EPA_ADMIN_TOKEN", "").strip()
PROVIDER = os.environ.get("EPA_PROVIDER", "SAO").strip().upper() or "SAO"
CLIENTES_EPA = [
    "ACHS",
    "ENTEL TIENDA",
    "ENTEL CAPITAL HUMANO",
    "CGE",
    "DIBAM/SNPC",
    "IDEMIA",
    "BANCO SECURITY",
    "AFC",
    "CAJA LOS HEROES",
    "COPEC",
    "UC Christus",
    "BUPA",
]
LOGO_TRANSPARENT_PATH = APP_DIR / "logo_entel_transparente.png"
TOWER_ART_PATH = APP_DIR / "torre_entel_lateral_opaca.png"
CATALOG_XLSX = Path(os.environ.get("EPA_CATALOG_XLSX", APP_DIR.parent / "SAO_2026.xlsx"))

QUESTIONS = [
    ("q1", "Califica la puntualidad del t\u00e9cnico respecto del horario acordado."),
    ("q2", "Califica la cordialidad y presentaci\u00f3n profesional del t\u00e9cnico."),
    ("q3", "Califica qu\u00e9 tan completa fue la soluci\u00f3n entregada a tu requerimiento."),
    ("q4", "Califica la calidad general de la atenci\u00f3n recibida."),
    ("q5", "Califica tu disposici\u00f3n a recomendar el servicio recibido."),
]


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


CSS = r"""
:root {
    color-scheme: light;
    --blue: #004ecb;
    --blue-strong: #003fa8;
    --blue-soft: #edf4ff;
    --orange: #ff6b1a;
    --green: #2faa54;
    --ink: #07162f;
    --muted: #59667a;
    --line: #d9e0ea;
    --page: #f6f8fb;
    --white: #ffffff;
    --danger: #b42318;
    --warning: #9a6700;
    --shadow: 0 18px 50px rgba(16, 36, 64, 0.14);
    --neon-cyan: #2ecbf2;
    --neon-blue: #005cff;
    --neon-pink: #fd6c98;
}

* {
    box-sizing: border-box;
}

html {
    min-height: 100%;
    color-scheme: light;
    -webkit-text-size-adjust: 100%;
    text-size-adjust: 100%;
}

body {
    min-height: 100vh;
    margin: 0;
    font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
    color: var(--ink);
    background:
        radial-gradient(circle at 12% 8%, rgba(0, 78, 203, 0.10), transparent 28rem),
        linear-gradient(145deg, #ffffff 0%, var(--page) 52%, #eef5ff 100%);
}

button,
input,
select,
textarea {
    font: inherit;
    color-scheme: light;
}

.page {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 24px;
}

@supports (min-height: 100dvh) {
    body,
    .page {
        min-height: 100dvh;
    }
}

.app-shell,
.admin-shell {
    width: min(100%, 620px);
}

.admin-shell {
    width: min(100%, 1180px);
}

.panel,
.admin-panel {
    overflow: hidden;
    background: var(--white);
    border: 1px solid rgba(0, 78, 203, 0.16);
    border-radius: 8px;
    box-shadow:
        var(--shadow),
        0 0 0 1px rgba(46, 203, 242, 0.16),
        0 0 34px rgba(46, 203, 242, 0.18);
}

.panel::before,
.admin-panel::before {
    content: "";
    display: block;
    height: 7px;
    background: linear-gradient(90deg, var(--blue), var(--neon-cyan) 58%, var(--orange));
    box-shadow: 0 0 18px rgba(46, 203, 242, 0.62), 0 0 28px rgba(253, 108, 152, 0.25);
}

.panel-inner,
.admin-inner {
    padding: 28px;
}

.header,
.admin-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}

.header {
    margin-bottom: 20px;
}

.brand {
    display: inline-flex;
    align-items: center;
    gap: 0;
    color: var(--blue);
    font-weight: 800;
    line-height: 1;
}

.brand-image {
    width: 158px;
    max-width: 100%;
    height: auto;
    display: block;
    object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(46, 203, 242, 0.20));
}

.brand-mark {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    font-size: 42px;
    letter-spacing: 0;
}

.brand-word {
    font-size: 24px;
}

.brand-e {
    color: var(--blue);
}

.brand-paren {
    color: var(--orange);
}

.tag,
.pill {
    display: inline-flex;
    align-items: center;
    min-height: 32px;
    padding: 6px 10px;
    border: 1px solid #cddbf7;
    border-radius: 999px;
    background: var(--blue-soft);
    color: var(--blue-strong);
    font-size: 13px;
    font-weight: 800;
    white-space: nowrap;
    box-shadow: 0 0 16px rgba(46, 203, 242, 0.22);
}

.pill-green {
    border-color: #c9edd4;
    background: #ebfff1;
    color: #136c2e;
}

.pill-warn {
    border-color: #f2dfa8;
    background: #fff7df;
    color: var(--warning);
}

.progress {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin: 0 0 22px;
}

.progress-step {
    height: 5px;
    border-radius: 999px;
    background: #dfe7f2;
}

.progress-step.is-active {
    background: var(--blue);
    box-shadow: 0 0 14px rgba(0, 92, 255, 0.48);
}

.screen {
    display: none;
}

.screen.is-active {
    display: block;
}

.intro,
.thanks,
.blocked {
    text-align: center;
}

.visual,
.success-ring {
    width: 150px;
    height: 150px;
    margin: 10px auto 22px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: linear-gradient(145deg, #eef5ff, #ffffff);
    border: 1px solid #dbe8ff;
    box-shadow: inset 0 0 24px rgba(46, 203, 242, 0.13), 0 0 24px rgba(46, 203, 242, 0.14);
}

.success-ring {
    background: #e9f8ee;
    color: var(--green);
}

.visual svg {
    width: 94px;
    height: 94px;
}

.success-ring svg {
    width: 104px;
    height: 104px;
}

h1,
h2,
h3,
p {
    margin-top: 0;
}

h1 {
    margin-bottom: 12px;
    font-size: clamp(29px, 4vw, 38px);
    line-height: 1.12;
    letter-spacing: 0;
    overflow-wrap: anywhere;
}

h2 {
    margin-bottom: 8px;
    font-size: 24px;
    line-height: 1.25;
    letter-spacing: 0;
}

h3 {
    margin-bottom: 12px;
    font-size: 17px;
    letter-spacing: 0;
}

.lead {
    color: var(--muted);
    font-size: 17px;
    line-height: 1.55;
    margin-bottom: 22px;
    overflow-wrap: anywhere;
}

.time-note,
.support-note,
.notice,
.link-box {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 14px;
    min-height: 78px;
    padding: 16px;
    border: 1px solid #dce6f8;
    border-radius: 8px;
    background: #f1f6ff;
    color: var(--ink);
    line-height: 1.45;
    margin: 0 0 24px;
}

.notice {
    align-items: flex-start;
    justify-content: flex-start;
    text-align: left;
}

.link-box {
    display: none;
    align-items: stretch;
    flex-direction: column;
    margin-top: 14px;
}

.link-box.is-visible {
    display: flex;
}

.link-value {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #ffffff;
    color: var(--ink);
    font-family: Consolas, "Courier New", monospace;
    font-size: 13px;
    overflow-wrap: anywhere;
}

.time-note svg,
.support-note svg,
.notice svg {
    width: 36px;
    height: 36px;
    flex: 0 0 auto;
    color: var(--blue);
}

.privacy {
    margin: 24px -28px -28px;
    padding: 16px 24px;
    background: var(--blue);
    color: #ffffff;
    font-size: 14px;
    line-height: 1.4;
}

.privacy svg {
    width: 17px;
    height: 17px;
    vertical-align: -3px;
    margin-right: 6px;
}

.question {
    margin: 0 0 20px;
    padding: 0;
    border: 0;
}

.question legend {
    margin-bottom: 10px;
    font-weight: 800;
    line-height: 1.35;
}

.rating {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
    background: #ffffff;
}

.rating input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
}

.rating label {
    min-height: 46px;
    display: grid;
    place-items: center;
    border-right: 1px solid var(--line);
    cursor: pointer;
    font-weight: 800;
    color: #1d2b42;
    background: #ffffff;
    transition: background 120ms ease, color 120ms ease, box-shadow 120ms ease;
}

.rating label:last-child {
    border-right: 0;
}

.rating input:focus-visible + label {
    outline: 3px solid rgba(0, 78, 203, 0.24);
    outline-offset: -3px;
}

.rating input:checked + label {
    background: linear-gradient(180deg, var(--blue), var(--neon-blue));
    color: #ffffff;
    box-shadow: inset 0 -3px 0 var(--orange);
}

.rating label:hover {
    background: #f2f7ff;
}

.rating input:checked + label:hover {
    background: var(--blue);
}

.scale-labels {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
    margin-top: 7px;
    color: var(--muted);
    font-size: 12px;
}

.scale-labels span:nth-child(2) {
    text-align: center;
}

.scale-labels span:nth-child(3) {
    text-align: right;
}

.comments {
    margin-top: 10px;
}

.comments label,
.field label {
    display: block;
    margin-bottom: 8px;
    font-weight: 800;
}

.comments span,
.field span {
    color: var(--muted);
    font-weight: 500;
}

input,
select,
textarea {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 12px;
    color: var(--ink);
    background: #ffffff;
    -webkit-text-fill-color: var(--ink);
    caret-color: var(--blue);
}

textarea {
    min-height: 92px;
    resize: vertical;
}

input:focus,
select:focus,
textarea:focus {
    border-color: var(--blue);
    outline: 3px solid rgba(0, 78, 203, 0.12);
    background: #ffffff;
}

input::placeholder,
textarea::placeholder {
    color: #8a96a8;
    opacity: 1;
    -webkit-text-fill-color: #8a96a8;
}

.actions {
    display: grid;
    grid-template-columns: 1fr 1.65fr;
    gap: 12px;
    margin-top: 20px;
}

.button {
    min-height: 54px;
    border: 0;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 12px 18px;
    font-weight: 800;
    cursor: pointer;
    text-decoration: none;
}

.button-primary {
    width: 100%;
    background: linear-gradient(90deg, var(--blue), var(--neon-blue));
    color: #ffffff;
    box-shadow: 0 0 18px rgba(0, 92, 255, 0.32), inset 0 1px 0 rgba(255,255,255,0.18);
}

.button-primary:hover {
    background: var(--blue-strong);
}

.button-secondary {
    background: #ffffff;
    color: var(--blue);
    border: 1px solid var(--blue);
}

.button:disabled {
    cursor: not-allowed;
    opacity: 0.62;
}

.status {
    min-height: 24px;
    margin-top: 12px;
    color: var(--danger);
    font-weight: 700;
}

.status.ok {
    color: #176c32;
}

.support-note {
    margin-top: 28px;
    background: #f3f6fb;
}

.public-page {
    position: relative;
    overflow: hidden;
    place-items: center;
    padding: clamp(18px, 4vw, 36px);
    background:
        linear-gradient(rgba(46, 203, 242, 0.07) 1px, transparent 1px),
        linear-gradient(90deg, rgba(46, 203, 242, 0.07) 1px, transparent 1px),
        linear-gradient(124deg, #050b14 0%, #07101d 54%, #0b1d33 100%);
    background-size: 26px 26px, 26px 26px, auto;
}

.public-page::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
        linear-gradient(180deg, rgba(46, 203, 242, 0.16), transparent 26%),
        linear-gradient(90deg, rgba(0, 92, 255, 0.18), transparent 36%, transparent 68%, rgba(255, 61, 0, 0.16));
}

.public-layout {
    position: relative;
    z-index: 1;
    width: min(100%, 1040px);
    min-height: min(720px, calc(100vh - 72px));
    display: grid;
    grid-template-columns: minmax(270px, 0.74fr) minmax(480px, 1.26fr);
    overflow: hidden;
    border: 1px solid rgba(46, 203, 242, 0.46);
    border-radius: 10px;
    background: rgba(6, 13, 24, 0.94);
    box-shadow:
        0 26px 70px rgba(0, 0, 0, 0.38),
        0 0 0 1px rgba(0, 92, 255, 0.24),
        0 0 46px rgba(46, 203, 242, 0.34);
}

.public-layout::after {
    content: "";
    position: absolute;
    inset: 0;
    z-index: 5;
    pointer-events: none;
    border-radius: inherit;
    padding: 3px;
    background: conic-gradient(
        from var(--epa-border-angle, 0deg),
        rgba(46, 203, 242, 1),
        rgba(0, 92, 255, 1),
        rgba(46, 203, 242, 1),
        rgba(255, 107, 26, 1),
        rgba(255, 180, 64, 1),
        rgba(253, 108, 152, 0.95),
        rgba(46, 203, 242, 1)
    );
    -webkit-mask:
        linear-gradient(#000 0 0) content-box,
        linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    filter:
        drop-shadow(0 0 8px rgba(46, 203, 242, 0.92))
        drop-shadow(0 0 18px rgba(0, 92, 255, 0.52));
    animation: epaBorderFlow 3.6s linear infinite;
}

@property --epa-border-angle {
    syntax: "<angle>";
    initial-value: 0deg;
    inherits: false;
}

@keyframes epaBorderFlow {
    to {
        --epa-border-angle: 360deg;
    }
}

@supports (min-height: 100dvh) {
    .public-layout {
        min-height: min(720px, calc(100dvh - 72px));
    }
}

.client-rail {
    position: relative;
    min-height: 100%;
    padding: clamp(28px, 4vw, 42px) clamp(24px, 3.2vw, 34px);
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    gap: clamp(28px, 5vh, 46px);
    color: #eaf6ff;
    border-right: 1px solid rgba(46, 203, 242, 0.34);
    background:
        linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(180deg, rgba(8, 24, 43, 0.98), rgba(4, 11, 21, 0.98));
    background-size: 24px 24px, 24px 24px, auto;
}

.client-rail::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    height: 5px;
    background: linear-gradient(90deg, var(--blue), var(--neon-cyan), var(--orange));
    box-shadow: 0 0 18px rgba(46, 203, 242, 0.76);
}

.rail-brand .brand {
    color: #ffffff;
    filter: drop-shadow(0 0 14px rgba(46, 203, 242, 0.28));
}

.rail-brand .brand-image {
    width: 214px;
    filter: drop-shadow(0 0 16px rgba(46, 203, 242, 0.24));
}

.rail-copy {
    display: grid;
    gap: 10px;
    position: relative;
    z-index: 4;
    margin-top: clamp(12px, 3vh, 26px);
}

.rail-neon-copy {
    width: fit-content;
    margin: 0;
    padding: 2px 0 0;
    color: #b9f7ff;
    max-width: 18ch;
    font-size: clamp(15px, 1.42vw, 19px);
    line-height: 1.22;
    font-weight: 820;
    letter-spacing: 0.008em;
    text-transform: none;
    text-shadow:
        0 0 7px rgba(46, 203, 242, 0.80),
        0 0 15px rgba(46, 203, 242, 0.34),
        0 0 24px rgba(0, 92, 255, 0.22);
}

.rail-neon-copy::after {
    content: "";
    display: block;
    width: 68%;
    height: 2px;
    margin-top: 8px;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--neon-cyan), var(--blue), var(--orange));
    box-shadow:
        0 0 9px rgba(46, 203, 242, 0.76),
        0 0 16px rgba(255, 107, 26, 0.22);
}

.tower-art {
    position: absolute;
    left: 50%;
    bottom: -34px;
    width: min(90%, 278px);
    max-height: 70%;
    transform: translateX(-50%);
    opacity: 1;
    pointer-events: none;
    filter:
        drop-shadow(0 0 10px rgba(46, 203, 242, 0.20));
}

.tower-art::before {
    content: none;
    display: none;
}

.tower-art img {
    position: relative;
    z-index: 1;
    display: block;
    width: 100%;
    height: auto;
    max-height: min(575px, 69vh);
    object-fit: contain;
    opacity: 1;
    image-rendering: auto;
}

.public-layout .app-shell {
    width: 100%;
    min-height: 100%;
    display: flex;
}

.public-card {
    width: 100%;
    border: 0;
    border-radius: 0;
    background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 252, 255, 0.98) 55%, rgba(236, 249, 255, 0.96) 100%);
    box-shadow: none;
}

.public-card::before {
    height: 5px;
}

.public-card .panel-inner {
    min-height: 100%;
    display: flex;
    flex-direction: column;
    padding: clamp(24px, 3.5vw, 38px);
}

.public-card .header {
    justify-content: flex-end;
    margin-bottom: 18px;
}

.public-card .header .brand {
    display: none;
}

.public-card .tag {
    border-color: rgba(46, 203, 242, 0.56);
    background: rgba(46, 203, 242, 0.12);
    color: var(--blue-strong);
}

.public-card .progress {
    margin-bottom: 24px;
}

.public-card .intro .visual {
    width: 130px;
    height: 130px;
    margin: 2px auto 18px;
}

.public-card .intro .visual svg {
    width: 82px;
    height: 82px;
}

.public-card h1 {
    font-size: clamp(28px, 3vw, 34px);
}

.public-card .lead {
    margin-bottom: 18px;
    font-size: 16px;
}

.public-card .progress-step {
    background: #d7e7f6;
}

.public-card .progress-step.is-active {
    background: linear-gradient(90deg, var(--blue), var(--neon-cyan));
}

.public-card .visual,
.public-card .success-ring {
    border-color: rgba(46, 203, 242, 0.42);
    background: linear-gradient(145deg, #f4fbff, #ffffff);
    box-shadow:
        inset 0 0 28px rgba(46, 203, 242, 0.16),
        0 0 28px rgba(46, 203, 242, 0.18);
}

.public-card .time-note,
.public-card .support-note {
    min-height: 68px;
    margin-bottom: 18px;
    border-color: rgba(46, 203, 242, 0.30);
    background: linear-gradient(90deg, rgba(237, 246, 255, 0.98), rgba(246, 251, 255, 0.98));
    box-shadow: inset 4px 0 0 rgba(46, 203, 242, 0.88);
}

.public-card .rating {
    border-color: #cfe3f3;
    box-shadow: 0 0 0 1px rgba(46, 203, 242, 0.10), 0 10px 24px rgba(7, 22, 47, 0.06);
}

.public-card .rating label {
    color: #073f8f;
}

.public-card .rating input:checked + label {
    background: linear-gradient(180deg, var(--blue), var(--neon-blue));
    box-shadow: inset 0 -3px 0 var(--orange), 0 0 16px rgba(0, 92, 255, 0.22);
}

.public-card input,
.public-card textarea {
    border-color: #cfe3f3;
}

.public-card .button-primary {
    background: linear-gradient(90deg, #10069f 0%, var(--neon-blue) 58%, var(--neon-cyan) 100%);
    box-shadow: 0 0 20px rgba(0, 92, 255, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.22);
}

.public-card .button {
    min-height: 52px;
}

.public-card .button-secondary {
    border-color: rgba(0, 92, 255, 0.48);
    color: var(--blue-strong);
    background: rgba(255, 255, 255, 0.82);
}

.public-card .privacy {
    margin-top: 20px;
    padding-top: 14px;
    padding-bottom: 14px;
    background: linear-gradient(90deg, #07162f 0%, var(--blue) 62%, #10069f 100%);
    border-top: 1px solid rgba(46, 203, 242, 0.36);
}

.admin-brandbar {
    position: relative;
    margin: -28px -28px 24px;
    padding: 22px 28px;
    border-bottom: 1px solid rgba(46, 203, 242, 0.36);
    background:
        linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(115deg, #050b14 0%, #07162f 58%, #0b1d33 100%);
    background-size: 24px 24px, 24px 24px, auto;
    box-shadow: inset 0 -1px 0 rgba(46, 203, 242, 0.20), 0 14px 30px rgba(46, 203, 242, 0.10);
}

.admin-brandbar::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    height: 5px;
    background: linear-gradient(90deg, var(--blue), var(--neon-cyan), var(--orange));
    box-shadow: 0 0 18px rgba(46, 203, 242, 0.72);
}

.admin-brandbar .brand-image {
    width: 184px;
}

.admin-brandbar .tag {
    border-color: rgba(46, 203, 242, 0.50);
    background: rgba(46, 203, 242, 0.12);
    color: #eaf6ff;
}

.row-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    min-width: 178px;
}

.button-compact {
    min-height: 38px !important;
    padding: 8px 11px !important;
    font-size: 13px !important;
}

.button-danger {
    border: 1px solid rgba(253, 108, 152, 0.72);
    background: linear-gradient(90deg, #fff7fa, #ffffff);
    color: #b42318;
    box-shadow: 0 0 14px rgba(253, 108, 152, 0.18);
}

.button-danger:hover:not(:disabled),
a.button-danger:hover {
    background: linear-gradient(90deg, #ffeaf1, #ffffff);
}

a.button-danger {
    text-decoration: none;
    opacity: 1 !important;
    cursor: pointer !important;
}

.admin-top {
    align-items: flex-start;
    margin-bottom: 20px;
}

.admin-title p {
    margin-bottom: 0;
    color: var(--muted);
}

.admin-actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    justify-content: flex-end;
}

.admin-actions .button,
.inline-actions .button {
    min-height: 42px;
    padding: 10px 13px;
    font-size: 14px;
}

.metric-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin: 22px 0;
}

.metric {
    min-height: 108px;
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #ffffff;
}

.metric span {
    display: block;
    color: var(--muted);
    font-size: 13px;
    font-weight: 700;
}

.metric strong {
    display: block;
    margin-top: 10px;
    font-size: 30px;
    line-height: 1;
}

.admin-grid {
    display: grid;
    grid-template-columns: minmax(360px, 0.72fr) minmax(520px, 1.28fr);
    gap: 18px;
    align-items: start;
}

.tool-panel {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 18px;
    background: #ffffff;
}

.form-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
}

.field-full {
    grid-column: 1 / -1;
}

.table-wrap {
    overflow-x: auto;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #ffffff;
    margin: 0 0 22px;
}

table {
    width: 100%;
    border-collapse: collapse;
    min-width: 840px;
}

th,
td {
    padding: 12px 14px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
}

th {
    background: #f6f8fb;
    color: #2c3b52;
    font-size: 13px;
    text-transform: uppercase;
}

tr:last-child td {
    border-bottom: 0;
}

.score-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 48px;
    min-height: 30px;
    padding: 5px 9px;
    border-radius: 999px;
    background: #eef5ff;
    color: var(--blue);
    font-weight: 800;
}

.mono {
    font-family: Consolas, "Courier New", monospace;
}

.nowrap {
    white-space: nowrap;
}

@media (max-width: 900px) {
    .admin-grid,
    .form-grid {
        grid-template-columns: 1fr;
    }

    .field-full {
        grid-column: auto;
    }
}

@media (max-width: 760px) {
    .page {
        padding: 0;
        place-items: stretch;
    }

    .app-shell,
    .admin-shell {
        width: 100%;
        min-height: 100vh;
    }

    .panel,
    .admin-panel {
        min-height: 100vh;
        border-radius: 0;
        border-left: 0;
        border-right: 0;
    }

    .panel-inner,
    .admin-inner {
        padding: 22px 18px;
    }

    .privacy {
        margin: 24px -18px -22px;
    }

    .brand-mark {
        font-size: 34px;
    }

    .brand-word {
        font-size: 20px;
    }

    .brand-image {
        width: 132px;
    }

    h1 {
        font-size: 30px;
    }

    .actions {
        grid-template-columns: 1fr;
    }

    .metric-grid {
        grid-template-columns: 1fr 1fr;
    }

    .admin-top {
        display: block;
    }

    .admin-actions {
        justify-content: flex-start;
        margin-top: 16px;
    }

    .public-page {
        overflow: auto;
    }

    .public-layout {
        width: 100%;
        min-height: 100vh;
        grid-template-columns: 1fr;
        border: 0;
        border-radius: 0;
        box-shadow: none;
    }

    .client-rail {
        min-height: auto;
        padding: 22px 18px 16px;
        gap: 12px;
        border-right: 0;
        border-bottom: 1px solid rgba(46, 203, 242, 0.34);
    }

    .rail-brand .brand-image {
        width: 132px;
    }

    .rail-copy {
        display: grid;
        gap: 4px;
    }

    .rail-neon-copy {
        max-width: 24ch;
        font-size: 14px;
        line-height: 1.18;
        letter-spacing: 0.004em;
    }

    .tower-art {
        display: none;
    }

    .public-layout .app-shell,
    .public-card {
        min-height: auto;
    }

    @supports (min-height: 100dvh) {
        .public-layout {
            min-height: 100dvh;
        }
    }

    .admin-brandbar {
        margin: -22px -18px 22px;
        padding: 18px;
    }

    .admin-brandbar .brand-image {
        width: 138px;
    }
}

@media (max-width: 430px) {
    .public-card .panel-inner {
        padding: 20px 16px;
    }

    .public-card .intro .visual {
        width: 112px;
        height: 112px;
        margin-bottom: 14px;
    }

    .public-card .intro .visual svg {
        width: 72px;
        height: 72px;
    }

    .public-card h1 {
        font-size: 27px;
    }

    .time-note,
    .support-note {
        align-items: flex-start;
        text-align: left;
    }

    .metric-grid {
        grid-template-columns: 1fr;
    }

    .rating label {
        min-height: 44px;
    }

    .header {
        align-items: flex-start;
    }
}

/* ===== Panel interno con estilo Entel neon ===== */
.admin-page {
    overflow: auto;
    place-items: center;
}

.admin-page .admin-shell {
    position: relative;
    z-index: 1;
    width: min(100%, 1220px);
}

.admin-page .admin-panel {
    background: rgba(6, 13, 24, 0.94);
    border: 1px solid rgba(46, 203, 242, 0.48);
    box-shadow:
        0 26px 70px rgba(0, 0, 0, 0.38),
        0 0 0 1px rgba(0, 92, 255, 0.24),
        0 0 46px rgba(46, 203, 242, 0.34);
}

.admin-page .admin-panel::before {
    height: 0;
}

.admin-page .admin-inner {
    color: #eaf6ff;
}

.admin-page .admin-brandbar {
    margin: -28px -28px 24px;
    border-bottom: 1px solid rgba(46, 203, 242, 0.34);
    background:
        linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(115deg, #050b14 0%, #07162f 58%, #0b1d33 100%);
    background-size: 24px 24px, 24px 24px, auto;
}

.admin-page .admin-title h1,
.admin-page h2 {
    color: #ffffff;
    text-shadow: 0 0 12px rgba(46, 203, 242, 0.30);
}

.admin-page .admin-title p,
.admin-page .lead {
    color: #b8c8dc;
}

.admin-page .metric,
.admin-page .tool-panel,
.admin-page .table-wrap {
    background: rgba(255, 255, 255, 0.97);
    color: var(--ink);
    border-color: rgba(46, 203, 242, 0.30);
    box-shadow: 0 0 0 1px rgba(46, 203, 242, 0.08), 0 16px 34px rgba(0, 0, 0, 0.14);
}

.admin-page .tool-panel h2,
.admin-page section > h2,
.admin-page .metric strong {
    color: var(--ink);
    text-shadow: none;
}

.admin-page .tool-panel .lead {
    color: var(--muted);
}

.admin-page .metric span {
    color: #52647b;
}

.admin-page table th {
    background: #eef5ff;
    color: #193555;
}

.admin-page input,
.admin-page select,
.admin-page textarea {
    background: #ffffff;
    color: var(--ink);
    -webkit-text-fill-color: var(--ink);
}

.admin-page .link-box {
    background: rgba(237, 246, 255, 0.98);
}

.admin-page .status.ok {
    color: #00a94f;
}

@media (max-width: 760px) {
    .admin-page {
        padding: 0;
        place-items: stretch;
    }
    .admin-page .admin-panel {
        border-radius: 0;
        border-left: 0;
        border-right: 0;
    }
}

"""


def normalize_catalog_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


DEMO_TECH_KEYWORDS = ("DEMO", "PRUEBA", "TEST")


def is_demo_or_test_technician(value: Any) -> bool:
    """Retorna True si el tecnico es de demostracion/prueba/test."""
    text = normalize_catalog_value(value).upper()
    if not text:
        return False
    return any(keyword in text for keyword in DEMO_TECH_KEYWORDS)


def purge_demo_or_test_records(conn: sqlite3.Connection) -> int:
    """Elimina atenciones y respuestas de tecnicos demo/prueba/test.

    Esto se ejecuta al iniciar la app, por lo que limpia incluso bases antiguas.
    """
    demo_rows = conn.execute(
        """
        SELECT id
        FROM atenciones
        WHERE UPPER(COALESCE(tecnico,'')) LIKE '%DEMO%'
           OR UPPER(COALESCE(tecnico,'')) LIKE '%PRUEBA%'
           OR UPPER(COALESCE(tecnico,'')) LIKE '%TEST%'
        """
    ).fetchall()
    demo_ids = [row["id"] if isinstance(row, sqlite3.Row) else row[0] for row in demo_rows]
    for attention_id in demo_ids:
        conn.execute("DELETE FROM respuestas WHERE atencion_id = ?", (attention_id,))
        conn.execute("DELETE FROM atenciones WHERE id = ?", (attention_id,))
    return len(demo_ids)


def xlsx_column_index(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha()).upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def read_xlsx_shared_strings(zfile: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zfile.namelist():
        return []
    root = ET.fromstring(zfile.read("xl/sharedStrings.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("x:si", ns):
        parts = [node.text or "" for node in item.findall(".//x:t", ns)]
        values.append("".join(parts))
    return values


def xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", ns))
    value = cell.find("x:v", ns)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value.text)]
        except (ValueError, IndexError):
            return ""
    return value.text


def read_panel_catalog() -> dict[str, Any]:
    regiones: set[str] = set()
    tecnicos: set[str] = set()
    tecnicos_por_region: dict[str, set[str]] = {}

    if CATALOG_XLSX.exists():
        try:
            with zipfile.ZipFile(CATALOG_XLSX) as zfile:
                shared_strings = read_xlsx_shared_strings(zfile)
                sheet_name = "xl/worksheets/sheet1.xml"
                if sheet_name not in zfile.namelist():
                    sheet_name = next(
                        (name for name in zfile.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")),
                        "",
                    )
                if sheet_name:
                    root = ET.fromstring(zfile.read(sheet_name))
                    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    parsed_rows: list[dict[int, str]] = []
                    for row in root.findall(".//x:sheetData/x:row", ns):
                        parsed: dict[int, str] = {}
                        for cell in row.findall("x:c", ns):
                            ref = cell.attrib.get("r", "")
                            parsed[xlsx_column_index(ref)] = normalize_catalog_value(xlsx_cell_text(cell, shared_strings))
                        if any(parsed.values()):
                            parsed_rows.append(parsed)

                    if parsed_rows:
                        headers = parsed_rows[0]
                        header_map = {value.lower(): index for index, value in headers.items() if value}
                        region_idx = next((header_map[key] for key in ("estado", "region", "región") if key in header_map), None)
                        tecnico_idx = next((header_map[key] for key in ("recurso", "tecnico", "técnico") if key in header_map), None)

                        for row in parsed_rows[1:]:
                            region = normalize_catalog_value(row.get(region_idx, "")) if region_idx is not None else ""
                            tecnico = normalize_catalog_value(row.get(tecnico_idx, "")) if tecnico_idx is not None else ""
                            if region:
                                regiones.add(region)
                            if tecnico and not is_demo_or_test_technician(tecnico):
                                tecnicos.add(tecnico)
                            if region and tecnico and not is_demo_or_test_technician(tecnico):
                                tecnicos_por_region.setdefault(region, set()).add(tecnico)
        except Exception:
            pass

    try:
        if DB_PATH.exists():
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                table_names = {
                    row["name"]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                if "atenciones" in table_names:
                    columns = {row["name"] for row in conn.execute("PRAGMA table_info(atenciones)").fetchall()}
                    if "region" in columns:
                        rows = conn.execute(
                            "SELECT DISTINCT region, tecnico FROM atenciones WHERE proveedor = ?",
                            (PROVIDER,),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT DISTINCT '' AS region, tecnico FROM atenciones WHERE proveedor = ?",
                            (PROVIDER,),
                        ).fetchall()
                    for row in rows:
                        region = normalize_catalog_value(row["region"])
                        tecnico = normalize_catalog_value(row["tecnico"])
                        if region:
                            regiones.add(region)
                        if tecnico and not is_demo_or_test_technician(tecnico):
                            tecnicos.add(tecnico)
                        if region and tecnico and not is_demo_or_test_technician(tecnico):
                            tecnicos_por_region.setdefault(region, set()).add(tecnico)
    except Exception:
        pass

    return {
        "regiones": sorted(regiones),
        "tecnicos": sorted(tecnicos),
        "tecnicos_por_region": {
            region: sorted(values)
            for region, values in sorted(tecnicos_por_region.items())
        },
    }


PUBLIC_JS = r"""
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const screens = {
    intro: $('[data-screen="intro"]'),
    form: $('[data-screen="form"]'),
    thanks: $('[data-screen="thanks"]'),
    blocked: $('[data-screen="blocked"]')
};
const statusBox = $('#formStatus');
const linkStatus = $('#linkStatus');
const startButton = $('[data-start]');
const progressSteps = $$('.progress-step');
const params = new URLSearchParams(window.location.search);

function tokenFromPath() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    if (parts.length >= 3 && parts[0].toLowerCase() === 'encuesta' && parts[1].toLowerCase() === 'entel') {
        return decodeURIComponent(parts[2] || '');
    }
    return '';
}

const publicToken = params.get('epa') || params.get('token') || tokenFromPath();
let attentionReady = false;

function screen(name) {
    Object.entries(screens).forEach(([key, element]) => {
        element.classList.toggle('is-active', key === name);
    });
    const step = name === 'intro' ? 0 : name === 'form' ? 1 : 2;
    progressSteps.forEach((element, index) => {
        element.classList.toggle('is-active', index <= step && name !== 'blocked');
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setBusy(isBusy) {
    const submit = $('#submitButton');
    submit.disabled = isBusy;
    submit.textContent = isBusy ? 'Enviando...' : 'Enviar encuesta';
}

async function validateAttention() {
    if (!publicToken) {
        $('#blockedTitle').textContent = 'Enlace EPA no asociado';
        $('#blockedText').textContent = 'Para responder esta encuesta debes usar el enlace unico enviado por Entel.';
        screen('blocked');
        return;
    }

    startButton.disabled = true;
    linkStatus.textContent = 'Validando enlace EPA...';
    try {
        const response = await fetch('/api/atencion-publica?epa=' + encodeURIComponent(publicToken));
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || 'Este enlace EPA no esta disponible.');
        }
        if (data.respondida) {
            $('#blockedTitle').textContent = 'Respuesta ya registrada';
            $('#blockedText').textContent = 'Ya recibimos la evaluacion asociada a esta atencion.';
            screen('blocked');
            return;
        }
        attentionReady = true;
        startButton.disabled = false;
        linkStatus.textContent = 'Encuesta lista para responder.';
        linkStatus.classList.add('ok');
    } catch (error) {
        $('#blockedTitle').textContent = 'Enlace EPA no valido';
        $('#blockedText').textContent = error.message || 'No pudimos validar esta atencion.';
        screen('blocked');
    }
}

$('[data-start]').addEventListener('click', () => {
    if (attentionReady) screen('form');
});
$('[data-back]').addEventListener('click', () => screen('intro'));
$('[data-home]').addEventListener('click', () => {
    $('#surveyForm').reset();
    statusBox.textContent = '';
    screen('intro');
});

$('#surveyForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    statusBox.textContent = '';

    const form = new FormData(event.currentTarget);
    const payload = {
        epa: publicToken,
        q1: form.get('q1'),
        q2: form.get('q2'),
        q3: form.get('q3'),
        q4: form.get('q4'),
        q5: form.get('q5'),
        comentario: String(form.get('comentario') || '').trim()
    };

    const missing = ['q1', 'q2', 'q3', 'q4', 'q5'].some((key) => !payload[key]);
    if (missing) {
        statusBox.textContent = 'Marca una nota en cada pregunta para continuar.';
        return;
    }

    setBusy(true);
    try {
        const response = await fetch('/api/respuestas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || 'No pudimos registrar la respuesta.');
        }
        screen('thanks');
    } catch (error) {
        statusBox.textContent = error.message || 'No pudimos registrar la respuesta.';
    } finally {
        setBusy(false);
    }
});

validateAttention();
"""


ADMIN_JS = r"""
const tokenQuery = window.location.search;
const withToken = (path) => path + tokenQuery;
const fmt = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 2 });
const dateFmt = new Intl.DateTimeFormat('es-CL', { dateStyle: 'short', timeStyle: 'short' });

function text(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function score(value) {
    if (value === null || value === undefined) return '-';
    return fmt.format(value);
}

function publicLink(token) {
    const params = new URLSearchParams(window.location.search);
    const configuredBase = (params.get('public_base') || '').replace(/\/+$/, '');
    const base = configuredBase || window.location.origin;
    return base + '/encuesta/entel/' + encodeURIComponent(token);
}

const catalogNode = document.querySelector('#catalogData');
const catalog = catalogNode ? JSON.parse(catalogNode.textContent || '{}') : {};

function setSelectOptions(select, values, placeholder) {
    const current = select.value;
    const cleaned = Array.from(new Set((values || []).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'es'));
    select.innerHTML = '';
    const first = document.createElement('option');
    first.value = '';
    first.textContent = cleaned.length ? placeholder : 'Sin datos disponibles';
    first.disabled = true;
    select.appendChild(first);

    cleaned.forEach((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    });

    select.value = cleaned.includes(current) ? current : '';
}

function isDemoOrTestTechnician(value) {
    const textValue = String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
    return ['DEMO', 'PRUEBA', 'TEST'].some((keyword) => textValue.includes(keyword));
}

function updateTechnicianOptions() {
    const regionSelect = document.querySelector('#region');
    const technicianSelect = document.querySelector('#tecnico');
    if (!regionSelect || !technicianSelect) return;
    const region = regionSelect.value;
    const byRegion = catalog.tecnicos_por_region || {};
    const valuesRaw = region && byRegion[region] ? byRegion[region] : (catalog.tecnicos || []);
    const values = valuesRaw.filter((value) => !isDemoOrTestTechnician(value));
    setSelectOptions(technicianSelect, values, 'Selecciona tecnico');
}

function initCatalogSelectors() {
    const regionSelect = document.querySelector('#region');
    if (!regionSelect) return;
    setSelectOptions(regionSelect, catalog.regiones || [], 'Selecciona region');
    regionSelect.addEventListener('change', updateTechnicianOptions);
    updateTechnicianOptions();
}

function renderMetrics(summary) {
    document.querySelector('#totalAtenciones').textContent = summary.total_atenciones;
    document.querySelector('#respondidas').textContent = summary.respondidas;
    document.querySelector('#pendientes').textContent = summary.pendientes;
    document.querySelector('#avg').textContent = score(summary.promedio_general);
}

function renderAttentionRows(rows) {
    const body = document.querySelector('#attentionRows');
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="10">Aun no hay atenciones EPA creadas.</td></tr>';
        return;
    }
    body.innerHTML = rows.map((row) => {
        const estado = row.respondida ? '<span class="pill pill-green">Respondida</span>' : '<span class="pill pill-warn">Pendiente</span>';
        const link = publicLink(row.public_token);
        const promedio = row.promedio === null || row.promedio === undefined ? '-' : `<span class="score-pill">${score(row.promedio)}</span>`;
        const label = `${row.cliente || 'cliente'} / ${row.contacto || 'usuario atendido'}`;
        const state = row.respondida ? 'respondida' : 'pendiente';
        const deleteUrl = `/admin/eliminar?id=${encodeURIComponent(row.id)}${tokenQuery ? '&' + tokenQuery.slice(1) : ''}`;
        const deleteButton = `<a class="button button-danger button-compact" href="${text(deleteUrl)}" data-delete-attention="${text(row.id)}" data-delete-label="${text(label)}" data-delete-state="${state}" title="Eliminar como administrador">Eliminar</a>`;
        return `
            <tr>
                <td>${estado}</td>
                <td>
                    <div class="row-actions">
                        <button class="button button-secondary button-compact" type="button" data-copy="${text(link)}">Copiar</button>
                        ${deleteButton}
                    </div>
                </td>
                <td>${text(row.cliente)}</td>
                <td>${text(row.contacto || '')}</td>
                <td>${text(row.region || '')}</td>
                <td>${text(row.tecnico)}</td>
                <td>${text(row.fecha_atencion || '')}</td>
                <td>${promedio}</td>
                <td>${text(row.comentario || '')}</td>
                <td class="mono">${text(row.public_token.slice(0, 10))}</td>
            </tr>
        `;
    }).join('');
}

function renderTechnicians(rows) {
    const body = document.querySelector('#technicianRows');
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="8">Aun no hay respuestas asociadas a tecnicos.</td></tr>';
        return;
    }
    body.innerHTML = rows.map((row) => `
        <tr>
            <td>${text(row.tecnico)}</td>
            <td>${row.total}</td>
            <td><span class="score-pill">${score(row.promedio_general)}</span></td>
            <td>${score(row.q1)}</td>
            <td>${score(row.q2)}</td>
            <td>${score(row.q3)}</td>
            <td>${score(row.q4)}</td>
            <td>${score(row.q5)}</td>
        </tr>
    `).join('');
}

function renderLatest(rows) {
    const body = document.querySelector('#latestRows');
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="9">Aun no hay respuestas registradas.</td></tr>';
        return;
    }
    body.innerHTML = rows.map((row) => {
        const created = row.created_at ? dateFmt.format(new Date(row.created_at)) : '';
        return `
            <tr>
                <td>${text(created)}</td>
                <td>${text(row.cliente)}</td>
                <td>${text(row.contacto || '')}</td>
                <td>${text(row.region || '')}</td>
                <td>${text(row.tecnico)}</td>
                <td><span class="score-pill">${score(row.promedio)}</span></td>
                <td>${row.q1}/${row.q2}/${row.q3}/${row.q4}/${row.q5}</td>
                <td>${text(row.comentario || '')}</td>
                <td class="mono">${text(row.id.slice(0, 8))}</td>
            </tr>
        `;
    }).join('');
}

async function load() {
    const status = document.querySelector('#adminStatus');
    status.textContent = 'Cargando datos...';
    try {
        const response = await fetch(withToken('/api/resumen'));
        const summary = await response.json();
        if (!response.ok || !summary.ok) {
            throw new Error(summary.error || 'No fue posible cargar el panel.');
        }
        renderMetrics(summary);
        renderAttentionRows(summary.atenciones);
        renderTechnicians(summary.por_tecnico);
        renderLatest(summary.ultimas);
        document.querySelector('#csvLink').href = withToken('/api/export.csv');
        document.querySelector('#jsonLink').href = withToken('/api/export.json');
        status.textContent = '';
    } catch (error) {
        status.textContent = error.message || 'No fue posible cargar el panel.';
    }
}

async function createAttention(event) {
    event.preventDefault();
    const status = document.querySelector('#createStatus');
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    status.classList.remove('ok');
    status.textContent = 'Creando atencion... EPA Admin V5 activo';
    try {
        const response = await fetch(withToken('/api/atenciones'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
            throw new Error(result.error || 'No fue posible crear la atencion.');
        }
        const link = publicLink(result.atencion.public_token);
        document.querySelector('#generatedLink').textContent = link;
        document.querySelector('#generatedLinkBox').classList.add('is-visible');
        document.querySelector('#copyGenerated').dataset.copy = link;
        status.classList.add('ok');
        status.textContent = 'Atencion creada. Link EPA listo para enviar.';
        form.reset();
        updateTechnicianOptions();
        await load();
    } catch (error) {
        status.textContent = error.message || 'No fue posible crear la atencion.';
    }
}

document.querySelector('#attentionForm').addEventListener('submit', createAttention);
document.addEventListener('click', async (event) => {
    const deleteButton = event.target.closest('[data-delete-attention]');
    if (deleteButton) {
        event.preventDefault();
        const status = document.querySelector('#adminStatus');
        const label = deleteButton.dataset.deleteLabel || 'esta EPA';
        const state = deleteButton.dataset.deleteState || 'pendiente';
        const warning = state === 'respondida'
            ? `Eliminar ${label}? Esta EPA ya fue respondida. Se eliminara la atencion y tambien su respuesta registrada. Esta accion no se puede deshacer.`
            : `Eliminar ${label}? Se eliminara el link EPA pendiente. Esta accion no se puede deshacer.`;
        if (!window.confirm(warning)) {
            return;
        }
        const old = deleteButton.textContent;
        deleteButton.disabled = true;
        deleteButton.textContent = 'Eliminando...';
        status.classList.remove('ok');
        status.textContent = 'Eliminando EPA...';
        try {
            const response = await fetch(withToken('/api/atenciones/eliminar'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: deleteButton.dataset.deleteAttention })
            });
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.error || 'No fue posible eliminar la EPA.');
            }
            status.classList.add('ok');
            status.textContent = 'EPA eliminada correctamente.';
            await load();
        } catch (error) {
            status.textContent = error.message || 'No fue posible eliminar la EPA.';
            deleteButton.disabled = false;
            deleteButton.textContent = old;
        }
        return;
    }

    const button = event.target.closest('[data-copy]');
    if (!button) return;
    try {
        await navigator.clipboard.writeText(button.dataset.copy);
        const old = button.textContent;
        button.textContent = 'Copiado';
        setTimeout(() => button.textContent = old, 1200);
    } catch (_error) {
        window.prompt('Copia este link EPA', button.dataset.copy);
    }
});

initCatalogSelectors();
load();
"""


def brand_html() -> str:
    return """
    <div class="brand" aria-label="Entel">
        <img class="brand-image" src="/assets/logo-entel.png" alt="Entel">
    </div>
    """


def icon_clipboard() -> str:
    return """
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true">
        <rect x="22" y="18" width="52" height="64" rx="7" stroke="#004ecb" stroke-width="5"/>
        <path d="M38 19c0-5 4-9 10-9s10 4 10 9h8v13H30V19h8Z" fill="#edf4ff" stroke="#004ecb" stroke-width="5"/>
        <path d="m33 48 7 7 14-16" stroke="#004ecb" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M58 50h14M35 68h27" stroke="#004ecb" stroke-width="5" stroke-linecap="round"/>
        <circle cx="70" cy="62" r="19" fill="#004ecb"/>
        <path d="m70 50 4 8 9 1-7 6 2 9-8-5-8 5 2-9-7-6 9-1 4-8Z" fill="#ffffff"/>
    </svg>
    """


def icon_clock() -> str:
    return """
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <circle cx="24" cy="24" r="18" stroke="currentColor" stroke-width="4"/>
        <path d="M24 13v12l8 5" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """


def icon_lock() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </svg>
    """


def icon_success() -> str:
    return """
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true">
        <circle cx="48" cy="48" r="34" stroke="currentColor" stroke-width="6"/>
        <path d="m31 49 12 12 24-27" stroke="currentColor" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """


def icon_heart() -> str:
    return """
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <path d="M24 39s-14-8-14-20a8 8 0 0 1 14-5 8 8 0 0 1 14 5c0 12-14 20-14 20Z" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
    </svg>
    """


def icon_link() -> str:
    return """
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <path d="M19 29 29 19" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
        <path d="M21 14l3-3a10 10 0 0 1 14 14l-3 3M27 34l-3 3A10 10 0 0 1 10 23l3-3" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
    </svg>
    """


def question_html(name: str, text: str, index: int) -> str:
    radios = []
    for value in range(1, 6):
        input_id = f"{name}_{value}"
        radios.append(
            f'<input id="{input_id}" type="radio" name="{name}" value="{value}" required>'
            f'<label for="{input_id}">{value}</label>'
        )
    return f"""
    <fieldset class="question">
        <legend>{index}. {html.escape(text)}</legend>
        <div class="rating" role="radiogroup" aria-label="{html.escape(text)}">
            {''.join(radios)}
        </div>
        <div class="scale-labels" aria-hidden="true">
            <span>Muy malo</span>
            <span>Regular</span>
            <span>Excelente</span>
        </div>
    </fieldset>
    """


def public_page() -> str:
    questions = "\n".join(question_html(name, text, index) for index, (name, text) in enumerate(QUESTIONS, 1))
    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="color-scheme" content="light">
    <title>EPA Entel - Encuesta Post Atencion</title>
    <style>{CSS}</style>
</head>
<body>
    <main class="page public-page">
        <div class="public-layout">
            <aside class="client-rail" aria-label="Entel">
                <div class="rail-brand">
                    {brand_html()}
                </div>
                <div class="rail-copy">
                    <p class="rail-neon-copy">Ay&uacute;danos a mejorar la atenci&oacute;n del servicio t&eacute;cnico.</p>
                </div>
                <div class="tower-art" aria-hidden="true">
                    <img src="/assets/torre-entel.png" alt="">
                </div>
            </aside>

            <div class="app-shell">
            <section class="panel public-card" aria-label="Encuesta EPA Entel">
                <div class="panel-inner">
                    <header class="header">
                        {brand_html()}
                        <span class="tag">EPA</span>
                    </header>

                    <div class="progress" aria-hidden="true">
                        <span class="progress-step is-active"></span>
                        <span class="progress-step"></span>
                        <span class="progress-step"></span>
                    </div>

                    <section class="screen intro is-active" data-screen="intro">
                        <div class="visual">{icon_clipboard()}</div>
                        <h1>Encuesta de satisfacci&oacute;n post atenci&oacute;n</h1>
                        <div class="time-note">
                            {icon_clock()}
                            <span>Responder esta encuesta te tomar&aacute; <strong>menos de 1 minuto.</strong></span>
                        </div>
                        <button class="button button-primary" type="button" data-start disabled>Comenzar encuesta <span aria-hidden="true">&rarr;</span></button>
                        <div class="status" id="linkStatus" role="status" aria-live="polite"></div>
                        <p class="privacy">{icon_lock()}Tus respuestas son confidenciales y se utilizan para mejorar nuestros servicios.</p>
                    </section>

                    <section class="screen" data-screen="form">
                        <h2>Por favor, responde las siguientes preguntas</h2>
                        <p class="lead">Marca una nota del 1 al 5 seg&uacute;n tu experiencia.</p>
                        <form id="surveyForm">
                            {questions}
                            <div class="comments">
                                <label for="comentario">Comentarios adicionales <span>(opcional)</span></label>
                                <textarea id="comentario" name="comentario" maxlength="800" placeholder="Cu&eacute;ntanos m&aacute;s sobre tu experiencia..."></textarea>
                            </div>
                            <div class="actions">
                                <button class="button button-secondary" type="button" data-back><span aria-hidden="true">&larr;</span> Atr&aacute;s</button>
                                <button class="button button-primary" id="submitButton" type="submit">Enviar encuesta</button>
                            </div>
                            <div class="status" id="formStatus" role="alert" aria-live="polite"></div>
                        </form>
                    </section>

                    <section class="screen thanks" data-screen="thanks">
                        <div class="success-ring">{icon_success()}</div>
                        <h1>&iexcl;Muchas gracias!</h1>
                        <p class="lead">Tu opini&oacute;n ha sido registrada correctamente. Nos ayuda a seguir mejorando para entregarte un mejor servicio.</p>
                        <div class="support-note">
                            {icon_heart()}
                            <span>Si tienes otra consulta o necesitas ayuda, puedes comunicarte con nosotros a trav&eacute;s de nuestros canales oficiales.</span>
                        </div>
                        <button class="button button-primary" type="button" data-home>Volver al inicio</button>
                    </section>

                    <section class="screen blocked" data-screen="blocked">
                        <div class="visual">{icon_link()}</div>
                        <h1 id="blockedTitle">Enlace EPA no disponible</h1>
                        <p class="lead" id="blockedText">Para responder esta encuesta debes usar el enlace enviado por Entel.</p>
                    </section>
                </div>
            </section>
            </div>
        </div>
    </main>
    <script>{PUBLIC_JS}</script>
</body>
</html>"""


def admin_locked_page() -> str:
    quick_access = ""
    if ADMIN_TOKEN:
        admin_href = "/admin?token=" + urllib.parse.quote(ADMIN_TOKEN)
        quick_access = f"""
                        <div class="inline-actions">
                            <a class="button button-primary" href="{html.escape(admin_href, quote=True)}">Entrar al panel admin</a>
                        </div>"""

    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>EPA Entel - Panel protegido</title>
    <style>{CSS}</style>
</head>
<body>
    <main class="page public-page admin-page">
        <div class="admin-shell">
            <section class="admin-panel" aria-label="Panel protegido EPA Entel">
                <div class="admin-inner">
                    <header class="header admin-brandbar">
                        <img class="brand-image" src="/assets/logo-entel.png" alt="Entel">
                        <span class="tag">EPA protegida</span>
                    </header>
                    <div class="admin-top">
                        <div class="admin-title">
                            <h1>Panel protegido</h1>
                            <p>La EPA local esta activa. Para generar links o revisar respuestas abre el acceso administrativo con token.</p>
                        </div>
                    </div>
                    <section class="tool-panel">
                        <h2>Acceso administrador</h2>
                        <p class="lead">Usa el archivo <strong>Abrir_EPA_Entel_PUBLICO_V4.cmd</strong> o el enlace que aparece en la consola como <span class="mono">/admin?token=...</span>.</p>
                        <div class="status">Si ves esta pantalla, el servidor funciona; solo falta entrar con el enlace correcto.</div>
                        {quick_access}
                    </section>
                </div>
            </section>
        </div>
    </main>
</body>
</html>"""


def admin_page() -> str:
    token_note = ""
    if ADMIN_TOKEN:
        token_note = "<p>Panel protegido. Ingresa usando <span class=\"mono\">/admin?token=tu-clave</span>.</p>"
    catalog_json = json.dumps(read_panel_catalog(), ensure_ascii=False).replace("</", "<\\/")
    cliente_options_html = "\n".join(
        f'<option value="{html.escape(cliente)}">{html.escape(cliente)}</option>'
        for cliente in CLIENTES_EPA
    )

    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="color-scheme" content="light">
    <title>EPA Entel - Panel de resultados</title>
    <style>{CSS}</style>
</head>
<body>
    <main class="page public-page admin-page">
        <div class="admin-shell">
            <section class="admin-panel" aria-label="Panel EPA Entel">
                <div class="admin-inner">
                    <header class="header admin-brandbar">
                        {brand_html()}
                        <span class="tag">EPA Entel</span>
                    </header>

                    <div class="admin-top">
                        <div class="admin-title">
                            <h1>EPA Entel por atenci&oacute;n</h1>
                            <p>Crea links por cliente, usuario atendido y t&eacute;cnico; revisa respuestas trazables y exporta para dashboard.</p>
                            {token_note}
                        </div>
                        <div class="admin-actions">
                            <a class="button button-secondary" id="jsonLink" href="/api/export.json">JSON</a>
                            <a class="button button-primary" id="csvLink" href="/api/export.csv">CSV</a>
                        </div>
                    </div>

                    <div class="metric-grid" aria-label="Resumen">
                        <div class="metric"><span>Atenciones creadas</span><strong id="totalAtenciones">0</strong></div>
                        <div class="metric"><span>Respondidas</span><strong id="respondidas">0</strong></div>
                        <div class="metric"><span>Pendientes</span><strong id="pendientes">0</strong></div>
                        <div class="metric"><span>Promedio general</span><strong id="avg">-</strong></div>
                    </div>

                    <div class="admin-grid">
                        <section class="tool-panel" aria-label="Crear atencion EPA Entel">
                            <h2>Nueva atenci&oacute;n a evaluar</h2>
                            <p class="lead">Selecciona el cliente, identifica al usuario atendido y genera un link EPA &uacute;nico.</p>
                            <form id="attentionForm">
                                <div class="form-grid">
                                    <div class="field">
                                        <label for="cliente">Cliente</label>
                                        <select id="cliente" name="cliente" required>
                                            <option value="" selected disabled>Selecciona cliente</option>
                                            {cliente_options_html}
                                        </select>
                                    </div>
                                    <div class="field">
                                        <label for="usuario_atendido">Nombre de usuario atendido</label>
                                        <input id="usuario_atendido" name="usuario_atendido" required maxlength="160" placeholder="Nombre y apellido del usuario">
                                    </div>
                                    <div class="field">
                                        <label for="ticket">Ticket <span>(opcional)</span></label>
                                        <input id="ticket" name="ticket" maxlength="120" placeholder="Ticket asociado">
                                    </div>
                                    <div class="field">
                                        <label for="region">Regi&oacute;n</label>
                                        <select id="region" name="region" required></select>
                                    </div>
                                    <div class="field">
                                        <label for="tecnico">T&eacute;cnico</label>
                                        <select id="tecnico" name="tecnico" required></select>
                                    </div>
                                    <div class="field">
                                        <label for="fecha_atencion">Fecha atenci&oacute;n <span>(opcional)</span></label>
                                        <input id="fecha_atencion" name="fecha_atencion" type="date">
                                    </div>
                                    <div class="field field-full">
                                        <label for="observacion_interna">Observaci&oacute;n interna <span>(opcional)</span></label>
                                        <textarea id="observacion_interna" name="observacion_interna" maxlength="600" placeholder="Dato interno para seguimiento, si aplica"></textarea>
                                    </div>
                                </div>
                                <button class="button button-primary" type="submit">Generar link EPA</button>
                                <div class="status" id="createStatus" role="alert" aria-live="polite"></div>
                            </form>
                            <div class="link-box" id="generatedLinkBox">
                                <strong>Link listo para enviar</strong>
                                <div class="link-value" id="generatedLink"></div>
                                <button class="button button-secondary" id="copyGenerated" type="button" data-copy="">Copiar link</button>
                            </div>
                        </section>

                        <section>
                            <h2>Atenciones EPA</h2>
                            <div class="table-wrap">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Estado</th>
                                            <th>Acciones</th>
                                            <th>Cliente</th>
                                            <th>Usuario atendido</th>
                                            <th>Regi&oacute;n</th>
                                            <th>T&eacute;cnico</th>
                                            <th>Fecha</th>
                                            <th>Promedio</th>
                                            <th>Comentario</th>
                                            <th>Token</th>
                                        </tr>
                                    </thead>
                                    <tbody id="attentionRows"></tbody>
                                </table>
                            </div>
                        </section>
                    </div>

                    <h2>Promedio por t&eacute;cnico</h2>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>T&eacute;cnico</th>
                                    <th>Respuestas</th>
                                    <th>General</th>
                                    <th>Horario</th>
                                    <th>Cordialidad</th>
                                    <th>Resoluci&oacute;n</th>
                                    <th>Calidad</th>
                                    <th>Recomienda</th>
                                </tr>
                            </thead>
                            <tbody id="technicianRows"></tbody>
                        </table>
                    </div>

                    <h2>&Uacute;ltimas respuestas</h2>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Cliente</th>
                                    <th>Usuario atendido</th>
                                    <th>Regi&oacute;n</th>
                                    <th>T&eacute;cnico</th>
                                    <th>Promedio</th>
                                    <th>Notas</th>
                                    <th>Comentario</th>
                                    <th>ID</th>
                                </tr>
                            </thead>
                            <tbody id="latestRows"></tbody>
                        </table>
                    </div>
                    <div class="status" id="adminStatus" role="alert" aria-live="polite"></div>
                </div>
            </section>
        </div>
    </main>
    <script id="catalogData" type="application/json">{catalog_json}</script>
    <script>{ADMIN_JS}</script>
</body>
</html>"""


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row["name"] for row in rows}


def ensure_column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    if name not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS atenciones (
                id TEXT PRIMARY KEY,
                public_token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                proveedor TEXT NOT NULL DEFAULT 'SAO',
                cliente TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT '',
                st TEXT NOT NULL,
                ticket TEXT NOT NULL DEFAULT '',
                tecnico TEXT NOT NULL,
                fecha_atencion TEXT NOT NULL DEFAULT '',
                canal TEXT NOT NULL DEFAULT '',
                contacto TEXT NOT NULL DEFAULT '',
                servicio TEXT NOT NULL DEFAULT '',
                observacion_interna TEXT NOT NULL DEFAULT '',
                estado TEXT NOT NULL DEFAULT 'pendiente'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS respuestas (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                atencion_id TEXT NOT NULL DEFAULT '',
                proveedor TEXT NOT NULL DEFAULT 'SAO',
                ticket TEXT NOT NULL DEFAULT '',
                tecnico TEXT NOT NULL DEFAULT '',
                canal TEXT NOT NULL DEFAULT '',
                referencia TEXT NOT NULL DEFAULT '',
                q1 INTEGER NOT NULL,
                q2 INTEGER NOT NULL,
                q3 INTEGER NOT NULL,
                q4 INTEGER NOT NULL,
                q5 INTEGER NOT NULL,
                comentario TEXT NOT NULL DEFAULT '',
                ip TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT ''
            )
            """
        )
        ensure_column(conn, "atenciones", "region", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "respuestas", "atencion_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "respuestas", "proveedor", "TEXT NOT NULL DEFAULT 'SAO'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atenciones_token ON atenciones(public_token)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atenciones_region ON atenciones(region)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atenciones_st ON atenciones(st)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atenciones_tecnico ON atenciones(tecnico)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_respuestas_created_at ON respuestas(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_respuestas_atencion ON respuestas(atencion_id)")
        purge_demo_or_test_records(conn)
        conn.commit()


def clean_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    cleaned = str(value).strip()
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def clean_multiline(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def parse_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Las notas deben estar entre 1 y 5.") from exc
    if score < 1 or score > 5:
        raise ValueError("Las notas deben estar entre 1 y 5.")
    return score


def make_token() -> str:
    return secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:22]


def validate_attention_payload(payload: dict[str, Any]) -> dict[str, Any]:
    usuario_atendido = clean_text(payload.get("usuario_atendido") or payload.get("contacto"), 160)
    row = {
        "id": str(uuid.uuid4()),
        "public_token": make_token(),
        "created_at": now_iso(),
        "proveedor": PROVIDER,
        "cliente": clean_text(payload.get("cliente"), 160),
        "region": clean_text(payload.get("region"), 120),
        "st": "EPA",
        "ticket": clean_text(payload.get("ticket"), 120),
        "tecnico": clean_text(payload.get("tecnico"), 160),
        "fecha_atencion": clean_text(payload.get("fecha_atencion"), 20),
        "canal": "",
        "contacto": usuario_atendido,
        "servicio": "",
        "observacion_interna": clean_multiline(payload.get("observacion_interna"), 600),
        "estado": "pendiente",
    }
    if not row["cliente"] or row["cliente"] not in CLIENTES_EPA:
        raise ValueError("Selecciona un cliente valido.")
    if not row["contacto"]:
        raise ValueError("Ingresa el nombre del usuario atendido.")
    if not row["region"]:
        raise ValueError("Selecciona la region.")
    if not row["tecnico"]:
        raise ValueError("Selecciona el tecnico.")
    if is_demo_or_test_technician(row["tecnico"]):
        raise ValueError("Selecciona un tecnico valido. Los tecnicos Demo/Prueba/Test no se pueden usar.")
    return row


def insert_attention(row: dict[str, Any]) -> dict[str, Any]:
    with db_connect() as conn:
        for _attempt in range(3):
            try:
                conn.execute(
                    """
                    INSERT INTO atenciones (
                        id, public_token, created_at, proveedor, cliente, region, st, ticket, tecnico,
                        fecha_atencion, canal, contacto, servicio, observacion_interna, estado
                    )
                    VALUES (
                        :id, :public_token, :created_at, :proveedor, :cliente, :region, :st, :ticket, :tecnico,
                        :fecha_atencion, :canal, :contacto, :servicio, :observacion_interna, :estado
                    )
                    """,
                    row,
                )
                conn.commit()
                return row
            except sqlite3.IntegrityError:
                row["public_token"] = make_token()
        raise ValueError("No fue posible generar un token unico.")


def delete_pending_attention(attention_id: Any) -> dict[str, Any]:
    """Elimina una EPA completa, esté pendiente o respondida."""
    attention_id = clean_text(attention_id, 80)
    if not attention_id:
        raise ValueError("No se recibio la EPA a eliminar.")
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT
                a.id,
                a.proveedor,
                a.cliente,
                a.st,
                COUNT(r.id) AS response_count
            FROM atenciones a
            LEFT JOIN respuestas r ON r.atencion_id = a.id
            WHERE a.id = ?
            GROUP BY a.id
            """,
            (attention_id,),
        ).fetchone()
        if not row:
            raise ValueError("La EPA no existe o ya fue eliminada.")
        conn.execute("DELETE FROM respuestas WHERE atencion_id = ?", (attention_id,))
        conn.execute("DELETE FROM atenciones WHERE id = ?", (attention_id,))
        conn.commit()
        return {
            "id": row["id"],
            "proveedor": row["proveedor"],
            "cliente": row["cliente"],
            "st": row["st"],
            "respuestas_eliminadas": int(row["response_count"] or 0),
        }


def find_attention_by_token(token: str) -> dict[str, Any] | None:
    token = clean_text(token, 80)
    if not token:
        return None
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT
                a.*,
                COUNT(r.id) AS response_count
            FROM atenciones a
            LEFT JOIN respuestas r ON r.atencion_id = a.id
            WHERE a.public_token = ? AND a.proveedor = ?
            GROUP BY a.id
            """,
            (token, PROVIDER),
        ).fetchone()
    return dict(row) if row else None


def validate_response_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    attention = find_attention_by_token(payload.get("epa") or payload.get("token"))
    if not attention:
        raise ValueError("El enlace EPA no esta asociado a una atencion valida.")
    if int(attention.get("response_count") or 0) > 0:
        raise ValueError("Esta atencion ya tiene una respuesta registrada.")
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "atencion_id": attention["id"],
        "proveedor": PROVIDER,
        "ticket": attention["ticket"],
        "tecnico": attention["tecnico"],
        "canal": attention["canal"],
        "referencia": attention["st"],
        "comentario": clean_multiline(payload.get("comentario"), 800),
    }
    for key, _question in QUESTIONS:
        row[key] = parse_score(payload.get(key))
    return row, attention


def insert_response(row: dict[str, Any], ip: str, user_agent: str) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO respuestas (
                id, created_at, atencion_id, proveedor, ticket, tecnico, canal, referencia,
                q1, q2, q3, q4, q5, comentario, ip, user_agent
            )
            VALUES (
                :id, :created_at, :atencion_id, :proveedor, :ticket, :tecnico, :canal, :referencia,
                :q1, :q2, :q3, :q4, :q5, :comentario, :ip, :user_agent
            )
            """,
            {
                **row,
                "ip": clean_text(ip, 80),
                "user_agent": clean_text(user_agent, 260),
            },
        )
        conn.execute("UPDATE atenciones SET estado = 'respondida' WHERE id = ?", (row["atencion_id"],))
        conn.commit()


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def query_records() -> list[dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                a.id AS atencion_id,
                a.public_token,
                a.created_at AS atencion_creada,
                a.proveedor,
                a.cliente,
                a.region,
                a.st,
                a.ticket,
                a.tecnico,
                a.fecha_atencion,
                a.canal,
                a.contacto,
                a.servicio,
                a.observacion_interna,
                CASE WHEN r.id IS NULL THEN 0 ELSE 1 END AS respondida,
                r.id AS respuesta_id,
                r.created_at AS respuesta_creada,
                r.q1, r.q2, r.q3, r.q4, r.q5,
                ROUND((r.q1 + r.q2 + r.q3 + r.q4 + r.q5) / 5.0, 2) AS promedio,
                r.comentario
            FROM atenciones a
            LEFT JOIN respuestas r ON r.atencion_id = a.id
            WHERE a.proveedor = ?
            ORDER BY a.created_at DESC
            """,
            (PROVIDER,),
        ).fetchall()
    return rows_as_dicts(rows)


def query_summary() -> dict[str, Any]:
    with db_connect() as conn:
        overall = conn.execute(
            """
            SELECT
                COUNT(a.id) AS total_atenciones,
                SUM(CASE WHEN r.id IS NULL THEN 0 ELSE 1 END) AS respondidas,
                SUM(CASE WHEN r.id IS NULL THEN 1 ELSE 0 END) AS pendientes,
                ROUND(AVG((r.q1 + r.q2 + r.q3 + r.q4 + r.q5) / 5.0), 2) AS promedio_general
            FROM atenciones a
            LEFT JOIN respuestas r ON r.atencion_id = a.id
            WHERE a.proveedor = ?
            """,
            (PROVIDER,),
        ).fetchone()
        attentions = conn.execute(
            """
            SELECT
                a.id, a.public_token, a.created_at, a.cliente, a.st, a.ticket, a.tecnico,
                a.region, a.fecha_atencion, a.canal, a.contacto, a.servicio, a.observacion_interna,
                CASE WHEN r.id IS NULL THEN 0 ELSE 1 END AS respondida,
                ROUND((r.q1 + r.q2 + r.q3 + r.q4 + r.q5) / 5.0, 2) AS promedio,
                r.comentario
            FROM atenciones a
            LEFT JOIN respuestas r ON r.atencion_id = a.id
            WHERE a.proveedor = ?
            ORDER BY a.created_at DESC
            LIMIT 80
            """,
            (PROVIDER,),
        ).fetchall()
        by_technician = conn.execute(
            """
            SELECT
                a.tecnico,
                COUNT(r.id) AS total,
                ROUND(AVG((r.q1 + r.q2 + r.q3 + r.q4 + r.q5) / 5.0), 2) AS promedio_general,
                ROUND(AVG(r.q1), 2) AS q1,
                ROUND(AVG(r.q2), 2) AS q2,
                ROUND(AVG(r.q3), 2) AS q3,
                ROUND(AVG(r.q4), 2) AS q4,
                ROUND(AVG(r.q5), 2) AS q5
            FROM respuestas r
            JOIN atenciones a ON a.id = r.atencion_id
            WHERE a.proveedor = ?
            GROUP BY a.tecnico
            ORDER BY promedio_general DESC, total DESC, a.tecnico ASC
            """,
            (PROVIDER,),
        ).fetchall()
        latest = conn.execute(
            """
            SELECT
                r.id, r.created_at, a.cliente, a.contacto, a.region, a.st, a.ticket, a.tecnico,
                r.q1, r.q2, r.q3, r.q4, r.q5,
                ROUND((r.q1 + r.q2 + r.q3 + r.q4 + r.q5) / 5.0, 2) AS promedio,
                r.comentario
            FROM respuestas r
            JOIN atenciones a ON a.id = r.atencion_id
            WHERE a.proveedor = ?
            ORDER BY r.created_at DESC
            LIMIT 30
            """,
            (PROVIDER,),
        ).fetchall()

    return {
        "ok": True,
        "proveedor": PROVIDER,
        "total_atenciones": int(overall["total_atenciones"] or 0),
        "respondidas": int(overall["respondidas"] or 0),
        "pendientes": int(overall["pendientes"] or 0),
        "promedio_general": overall["promedio_general"],
        "atenciones": rows_as_dicts(attentions),
        "por_tecnico": rows_as_dicts(by_technician),
        "ultimas": rows_as_dicts(latest),
    }


def export_csv(records: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "proveedor",
        "atencion_id",
        "public_token",
        "atencion_creada",
        "cliente",
        "region",
        "st",
        "ticket",
        "tecnico",
        "fecha_atencion",
        "canal",
        "usuario_atendido",
        "servicio",
        "observacion_interna",
        "respondida",
        "respuesta_id",
        "respuesta_creada",
        "q1_horario",
        "q2_cordialidad",
        "q3_resolucion",
        "q4_calidad",
        "q5_recomendacion",
        "promedio",
        "comentario",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for record in records:
        writer.writerow(
            {
                "proveedor": record["proveedor"],
                "atencion_id": record["atencion_id"],
                "public_token": record["public_token"],
                "atencion_creada": record["atencion_creada"],
                "cliente": record["cliente"],
                "region": record.get("region", ""),
                "st": record["st"],
                "ticket": record["ticket"],
                "tecnico": record["tecnico"],
                "fecha_atencion": record["fecha_atencion"],
                "canal": record["canal"],
                "usuario_atendido": record["contacto"],
                "servicio": record["servicio"],
                "observacion_interna": record["observacion_interna"],
                "respondida": record["respondida"],
                "respuesta_id": record["respuesta_id"] or "",
                "respuesta_creada": record["respuesta_creada"] or "",
                "q1_horario": record["q1"] or "",
                "q2_cordialidad": record["q2"] or "",
                "q3_resolucion": record["q3"] or "",
                "q4_calidad": record["q4"] or "",
                "q5_recomendacion": record["q5"] or "",
                "promedio": record["promedio"] or "",
                "comentario": record["comentario"] or "",
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


class EpaHandler(BaseHTTPRequestHandler):
    server_version = "EPA-ENTEL/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(status, body.encode("utf-8"), "text/html; charset=utf-8")

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def parse_url(self) -> urllib.parse.ParseResult:
        return urllib.parse.urlparse(self.path)

    def is_admin_authorized(self) -> bool:
        if not ADMIN_TOKEN:
            return True
        parsed = self.parse_url()
        token = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
        return token == ADMIN_TOKEN or self.headers.get("X-Admin-Token", "") == ADMIN_TOKEN

    def require_admin(self) -> bool:
        if self.is_admin_authorized():
            return True
        self.send_json(
            {
                "ok": False,
                "error": "Panel protegido. Agrega ?token=tu-clave al enlace.",
            },
            HTTPStatus.UNAUTHORIZED,
        )
        return False

    def read_json_body(self, max_bytes: int = 64 * 1024) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > max_bytes:
            raise ValueError("La solicitud es demasiado grande.")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Formato invalido.")
        return payload

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT.value)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = self.parse_url()
        path = parsed.path.rstrip("/") or "/"
        try:
            if path in {"/", "/index.html"} or path.startswith("/encuesta/entel/"):
                self.send_html(public_page())
            elif path == "/assets/logo-entel.png":
                if LOGO_TRANSPARENT_PATH.exists():
                    self.send_bytes(HTTPStatus.OK, LOGO_TRANSPARENT_PATH.read_bytes(), "image/png")
                else:
                    self.send_bytes(HTTPStatus.NOT_FOUND, b"", "image/png")
            elif path == "/assets/torre-entel.png":
                if TOWER_ART_PATH.exists():
                    self.send_bytes(HTTPStatus.OK, TOWER_ART_PATH.read_bytes(), "image/png")
                else:
                    self.send_bytes(HTTPStatus.NOT_FOUND, b"", "image/png")
            elif path == "/admin/eliminar":
                if ADMIN_TOKEN and not self.is_admin_authorized():
                    self.send_html(admin_locked_page(), HTTPStatus.UNAUTHORIZED)
                else:
                    query = urllib.parse.parse_qs(parsed.query)
                    deleted = delete_pending_attention(query.get("id", [""])[0])
                    token = query.get("token", [""])[0]
                    back_url = "/admin" + (("?token=" + urllib.parse.quote(token)) if token else "")
                    self.send_html(
                        f"""<!doctype html>
<meta charset="utf-8">
<meta http-equiv="refresh" content="1; url={html.escape(back_url)}">
<title>EPA eliminada</title>
<style>
body{{font-family:Arial,sans-serif;background:#050b14;color:#eaf6ff;padding:40px}}
.card{{max-width:640px;margin:auto;border:1px solid #2ecbf2;border-radius:14px;padding:24px;background:#07162f;box-shadow:0 0 28px rgba(46,203,242,.28)}}
a{{color:#2ecbf2}}
</style>
<div class="card">
<h1>EPA eliminada correctamente</h1>
<p>Se eliminó la atención y sus respuestas asociadas, si existían.</p>
<p>Volviendo al panel...</p>
<p><a href="{html.escape(back_url)}">Volver ahora</a></p>
</div>""",
                        HTTPStatus.OK,
                    )
            elif path == "/admin":
                if ADMIN_TOKEN and not self.is_admin_authorized():
                    self.send_html(admin_locked_page(), HTTPStatus.UNAUTHORIZED)
                else:
                    self.send_html(admin_page())
            elif path == "/api/atencion-publica":
                query = urllib.parse.parse_qs(parsed.query)
                attention = find_attention_by_token(query.get("epa", [""])[0] or query.get("token", [""])[0])
                if not attention:
                    self.send_json({"ok": False, "error": "Enlace EPA no valido."}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_json(
                        {
                            "ok": True,
                            "respondida": int(attention.get("response_count") or 0) > 0,
                        }
                    )
            elif path == "/api/resumen":
                if self.require_admin():
                    self.send_json(query_summary())
            elif path == "/api/export.json":
                if self.require_admin():
                    self.send_bytes(
                        HTTPStatus.OK,
                        json.dumps({"ok": True, "proveedor": PROVIDER, "registros": query_records()}, ensure_ascii=False, indent=2).encode(
                            "utf-8"
                        ),
                        "application/json; charset=utf-8",
                        {"Content-Disposition": 'attachment; filename="epa_entel_registros.json"'},
                    )
            elif path == "/api/export.csv":
                if self.require_admin():
                    self.send_bytes(
                        HTTPStatus.OK,
                        export_csv(query_records()),
                        "text/csv; charset=utf-8",
                        {"Content-Disposition": 'attachment; filename="epa_entel_registros.csv"'},
                    )
            elif path == "/health":
                self.send_json({"ok": True, "service": "epa_entel"})
            elif path == "/favicon.ico":
                self.send_bytes(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            else:
                self.send_html("<h1>404</h1><p>Pagina no encontrada.</p>", HTTPStatus.NOT_FOUND)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = self.parse_url()
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/api/atenciones":
                if not self.require_admin():
                    return
                row = validate_attention_payload(self.read_json_body())
                inserted = insert_attention(row)
                self.send_json({"ok": True, "atencion": inserted}, HTTPStatus.CREATED)
            elif path == "/api/atenciones/eliminar":
                if not self.require_admin():
                    return
                deleted = delete_pending_attention(self.read_json_body().get("id"))
                self.send_json({"ok": True, "atencion": deleted})
            elif path == "/api/respuestas":
                row, _attention = validate_response_payload(self.read_json_body())
                insert_response(row, self.client_address[0], self.headers.get("User-Agent", ""))
                self.send_json({"ok": True, "id": row["id"], "created_at": row["created_at"]}, HTTPStatus.CREATED)
            else:
                self.send_json({"ok": False, "error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            self.send_json({"ok": False, "error": "JSON invalido."}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    strict_port = os.environ.get("EPA_STRICT_PORT", "").strip().lower() in {"1", "true", "si", "sí"}
    last_error: OSError | None = None
    attempts = [port] if strict_port else range(port, port + 25)
    for candidate in attempts:
        try:
            return ReusableThreadingHTTPServer((host, candidate), EpaHandler)
        except OSError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def main() -> int:
    init_db()
    server = build_server(DEFAULT_HOST, DEFAULT_PORT)
    host, port = server.server_address[:2]
    public_host = "127.0.0.1" if host in {"0.0.0.0", ""} else host
    base_url = f"http://{public_host}:{port}"
    admin_url = f"{base_url}/admin"
    if ADMIN_TOKEN:
        admin_url += "?token=" + urllib.parse.quote(ADMIN_TOKEN)

    print("")
    print("EPA Entel - Encuesta Post Atencion")
    print(f"EPA_PORT_ACTUAL={port}")
    print(f"Formulario publico: {base_url}/encuesta/entel/<token>")
    print(f"Panel resultados:   {admin_url}")
    print(f"Base de datos:      {DB_PATH}")
    print("Presiona Ctrl+C para detener.")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
