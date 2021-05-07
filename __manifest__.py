{
    'name': 'Equipment Repair',
    'version': '14.0.1.0.0',
    'author': 'Hibou Corp.',
    'category': 'Human Resources',
    'summary': 'Consumir productos en solicitudes de mantenimiento',
    'description': """
Reparación de equipos
================

Lleve un registro de las piezas necesarias para reparar el equipo..
""",
    'website': '',
    'depends': [
        'stock',
        'maintenance_notebook',
        'hr_department_project',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/maintenance_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
