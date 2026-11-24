% Motor de recomendaciones (programacion logica).
%
% Hechos (los carga Python desde las ventas):
%   compro(Cliente, Producto).
%
% Idea: a un cliente se le recomienda lo que compraron otros clientes
% "similares" (que comparten al menos dos productos con el) y que el aun no tiene.

:- dynamic compro/2.

% Cuantos productos en comun hacen falta para que dos clientes se parezcan.
% Si el cliente compro menos productos que eso, basta con que coincidan todos.
minimo_en_comun(2).

% Otro cliente que compro al menos uno de los productos de C.
candidato(C, Otro) :-
    compro(C, P),
    compro(Otro, P),
    C \== Otro.

en_comun(C, Otro, N) :-
    aggregate_all(count, ( compro(C, P), compro(Otro, P) ), N).

minimo_para(C, M) :-
    minimo_en_comun(Minimo),
    aggregate_all(count, compro(C, _), Propios),
    M is min(Minimo, Propios).

% Dos clientes son similares si comparten suficientes productos.
similar(C, Otro) :-
    setof(X, candidato(C, X), Candidatos),
    member(Otro, Candidatos),
    en_comun(C, Otro, N),
    minimo_para(C, M),
    N >= M.

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
