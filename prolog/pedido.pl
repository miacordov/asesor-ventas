% Armado de pedidos con backtracking (programacion logica).
%
% Hechos que carga Python:
%   producto(Id, Categoria, Centavos)   precio en CENTAVOS (enteros, sin errores
%                                       de redondeo de los decimales)
%   compro(Cliente, Producto)           definido en reglas.pl
%
% armar(+Presupuesto, +Categorias, -Productos, -Total)
%   Un producto por cada categoria pedida, sin repetir, sin pasarse del
%   presupuesto. Cada solucion es un pedido valido; el backtracking las
%   recorre todas. Presupuesto y Total estan en centavos.
%
% armar_para(+Cliente, +Presupuesto, +Categorias, -Productos, -Total)
%   Igual, pero sin ofrecerle productos que ese cliente ya compro.

:- dynamic producto/3.

sin_filtro(_).

no_comprado(Cliente, Producto) :-
    \+ compro(Cliente, Producto).

armar(Presupuesto, Categorias, Productos, Total) :-
    cubrir(Categorias, Presupuesto, sin_filtro, [], Productos, 0, Total).

armar_para(Cliente, Presupuesto, Categorias, Productos, Total) :-
    cubrir(Categorias, Presupuesto, no_comprado(Cliente), [], Productos, 0, Total).

% cubrir(+Categorias, +Max, +Filtro, +Acumulado, -Productos, +Total0, -Total)
% Filtro es un objetivo parcial: call(Filtro, Id) lo completa con el producto.
cubrir([], _, _, Acumulado, Productos, Total, Total) :-
    reverse(Acumulado, Productos).
cubrir([Categoria|Resto], Max, Filtro, Acumulado, Productos, Total0, Total) :-
    producto(Id, Categoria, Precio),
    \+ memberchk(Id, Acumulado),
    call(Filtro, Id),
    Total1 is Total0 + Precio,
    Total1 =< Max,
    cubrir(Resto, Max, Filtro, [Id|Acumulado], Productos, Total1, Total).
