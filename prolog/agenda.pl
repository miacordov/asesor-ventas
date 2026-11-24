% Reglas de la agenda comercial (programacion logica).
%
% Hechos que carga Python:
%   n_compras(Cliente, N)              dias distintos en que compro (en total)
%   compras_recientes(Cliente, N)      dias distintos en que compro en los ultimos 180 dias
%   intervalo_promedio(Cliente, Dias)  dias medios entre compras (solo con 2 o mas)
%   dias_sin_comprar(Cliente, Dias)    solo si ya compro alguna vez
%   umbral(frecuente, MinCompras)      desde cuantas compras recientes es frecuente
%   umbral(inactividad, MaxDias)       limite de inactividad de quien no tiene intervalo
% Depende de recomendar/2 (definida en reglas.pl).
%
% accion(Cliente, Tipo, Motivos): que conviene hacer con el cliente y por que.
% Los motivos son atomos; Python los convierte en frases para el vendedor.

:- dynamic n_compras/2, compras_recientes/2, intervalo_promedio/2, dias_sin_comprar/2, umbral/2.

% Nadie se considera inactivo antes de estos dias, por seguido que compre.
inactividad_minima(15).

% Frecuente: compro varias veces en los ultimos meses (no en toda su historia).
frecuente(C) :-
    umbral(frecuente, Minimo),
    compras_recientes(C, N),
    N >= Minimo.

% Cada cliente tiene su ritmo: esta inactivo cuando tarda 1,5 veces lo que
% suele tardar entre compras. Sin intervalo conocido se usa el umbral general.
limite_inactividad(C, Limite) :-
    intervalo_promedio(C, Intervalo), !,
    inactividad_minima(Minimo),
    Limite is max(Minimo, ceiling(1.5 * Intervalo)).
limite_inactividad(_, Limite) :-
    umbral(inactividad, Limite).

inactivo(C) :-
    dias_sin_comprar(C, Dias),
    limite_inactividad(C, Limite),
    Dias > Limite.

reciente(C) :-
    dias_sin_comprar(C, Dias),
    limite_inactividad(C, Limite),
    Dias =< Limite.

% Compraba seguido y dejo de venir: reactivarlo.
accion(C, reactivar, [frecuente, inactivo]) :-
    frecuente(C),
    inactivo(C).

% Compra seguido y esta activo: fidelizarlo.
accion(C, fidelizar, [frecuente, reciente]) :-
    frecuente(C),
    reciente(C).

% Compra poco pero hay productos que otros clientes parecidos si llevan.
accion(C, cruzar, [no_frecuente, similares]) :-
    n_compras(C, N),
    N >= 1,
    \+ frecuente(C),
    once(recomendar(C, _)).
