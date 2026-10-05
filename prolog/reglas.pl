% Motor de recomendaciones (programacion logica).
%
% Hechos (los carga Python desde las ventas):
%   compro(Cliente, Producto).
%
% Idea: a un cliente se le recomienda lo que compraron otros clientes
% "similares" (que comparten al menos un producto con el) y que el aun no tiene.

:- dynamic compro/2.

% Dos clientes son similares si compraron al menos un producto en comun.
similar(C, Otro) :-
    compro(C, P),
    compro(Otro, P),
    C \== Otro.

% Lista ordenada y sin repetidos de clientes similares ([] si no hay ninguno).
clientes_similares(C, Lista) :-
    setof(O, similar(C, O), Lista), !.
clientes_similares(_, []).

% Respaldo: los clientes similares a C que compraron P, cuando C aun no lo tiene.
% Con P sin instanciar, enumera cada producto candidato con su lista de respaldo.
respaldo(C, P, Lista) :-
    setof(O, ( similar(C, O), compro(O, P), \+ compro(C, P) ), Lista).

% Regla simple: se recomienda P a C si hay respaldo.
recomendar(C, P) :-
    respaldo(C, P, _).
