:- dynamic compro/2.

similar(C, Otro) :- compro(C, P), compro(Otro, P), C \== Otro.
recomendar(C, P) :- similar(C, Otro), compro(Otro, P), \+ compro(C, P).
