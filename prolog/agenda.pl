% Reglas de la agenda comercial (programacion logica).
%
% Hechos que carga Python:
%   n_compras(Cliente, N)              dias distintos en que compro
%   dias_sin_comprar(Cliente, Dias)    solo si ya compro alguna vez
%   umbral(frecuente, MinCompras)      desde cuantas compras es frecuente
%   umbral(inactividad, MaxDias)       desde cuantos dias se considera inactivo
% Depende de recomendar/2 (definida en reglas.pl).
%
% accion(Cliente, Tipo, Motivos): que conviene hacer con el cliente y por que.
% Los motivos son atomos; Python los convierte en frases para el vendedor.

:- dynamic n_compras/2, dias_sin_comprar/2, umbral/2.

frecuente(C) :-
    umbral(frecuente, Minimo),
    n_compras(C, N),
    N >= Minimo.

inactivo(C) :-
    umbral(inactividad, Maximo),
    dias_sin_comprar(C, Dias),
    Dias > Maximo.

reciente(C) :-
    umbral(inactividad, Maximo),
    dias_sin_comprar(C, Dias),
    Dias =< Maximo.

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
