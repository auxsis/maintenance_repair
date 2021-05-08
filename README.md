# maintenance_repair
Realizar reparaciones desde el modelo de mantenimiento

Modelo basado en mrp_repair para crear movimientos de stock

Se añade un capo de validación al product.template para marcar el producto como una parte.
se añade un nuevo menu y accion a maintenance, heredando la vista busqueda del product.template para crear Partes desde el modelo de Mantenimiento.
Se añade un nuevo menu dentro de Partes, el cual hereda el stock.quant con un filtro que permite ver el stock actual a mano por almacen.

Ahora el modelo de reparación, permite realizar stock.move con productos almacenables, asi como tambien permite validad nuemeros de serie si el producto tiene rastreo por nuemeros de serie.
Se añadio el campo lot_id relacionado al stock.production.lot para añadir y comparar los numeros de serie (Basado en el modelo original repair de odoo)
