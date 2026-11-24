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
%   Una combinacion lleva al menos MINIMO_PRODUCTOS productos: con una sola
%   categoria no hay combinacion (para dos productos de la misma categoria se
%   pide la categoria dos veces).
%
% armar_para(+Cliente, +Presupuesto, +Categorias, -Productos, -Total)
%   Igual, pero sin ofrecerle productos que ese cliente ya compro.

:- dynamic producto/3.

minimo_productos(2).

sin_filtro(_).

% Una sola categoria (o ninguna) no puede formar una combinacion.
combinable(Categorias) :-
    minimo_productos(Minimo),
    length(Categorias, N),
    N >= Minimo.

no_comprado(Cliente, Producto) :-
    \+ compro(Cliente, Producto).

armar(Presupuesto, Categorias, Productos, Total) :-
    combinable(Categorias),
    cubrir(Categorias, Presupuesto, sin_filtro, [], Productos, 0, Total).

armar_para(Cliente, Presupuesto, Categorias, Productos, Total) :-
    combinable(Categorias),
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

% Complementos: categorias que se usan juntas (la relacion vale en los dos sentidos).
% A quien compro una tarjeta grafica le sirve memoria RAM o un monitor, no otra grafica.
complementa(computo, perifericos).
complementa(computo, monitores).
complementa(computo, memoria_ram).
complementa(computo, almacenamiento).
complementa(computo, accesorios).
complementa(computo, audio).
complementa(computo, mobiliario).
complementa(graficas, memoria_ram).
complementa(graficas, monitores).
complementa(monitores, perifericos).
complementa(almacenamiento, memorias).

complementarias(A, B) :- complementa(A, B).
complementarias(A, B) :- complementa(B, A).

% Categorias que el cliente ya compro ([] si ninguna).
categorias_de(C, Categorias) :-
    setof(Cat, P^Precio^( compro(C, P), producto(P, Cat, Precio) ), Categorias), !.
categorias_de(_, []).

% complemento(+Cliente, -Categoria, -Producto, -Centavos)
%   Productos de categorias que complementan lo que compro y que aun no compra.
complemento(C, Categoria, P, Centavos) :-
    categorias_de(C, Suyas),
    setof(Cat, A^( member(A, Suyas), complementarias(A, Cat), \+ memberchk(Cat, Suyas) ), Categorias),
    member(Categoria, Categorias),
    producto(P, Categoria, Centavos).
