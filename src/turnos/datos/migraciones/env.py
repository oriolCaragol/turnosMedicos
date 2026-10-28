"""Entorno de Alembic. La conexión la proporciona `turnos.datos.bd.migrar`."""

from alembic import context

from turnos.datos.tablas import Base

conexion = context.config.attributes["conexion"]
context.configure(
    connection=conexion,
    target_metadata=Base.metadata,
    render_as_batch=True,  # SQLite no admite ALTER TABLE completo
)
with context.begin_transaction():
    context.run_migrations()
