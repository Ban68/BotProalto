// ── Configuración declarativa de las campañas Familia A ────────────
// Cada panel se monta en su contenedor [data-campaign="<id>"] dentro
// del estado correspondiente en admin.html. La lógica vive en
// campaign-panel.js; aquí solo se describen las diferencias.

const CampaignPanels = {};

[
    {
        id: 'envios',
        icon: '⚡',
        accent: '#4f46e5',
        title: 'Envíos Masivos: Aprobado por el cliente',
        description: 'Esta herramienta te permite notificar a todos los clientes que han sido aprobados y no han recibido un mensaje hoy.',
        templateName: 'estado_verde',
        fetchEndpoint: '/admin/api/pending-notifications',
        sendEndpoint: '/admin/api/trigger-bulk-send',
        confirm: n => `¿Estás seguro de enviar la notificación de Aprobado a ${n} clientes seleccionados?`,
        executeLabel: '🚀 Ejecutar Envío a Seleccionados',
        batchSize: 15,
        features: { empresa: true, soloNuevos: true, lastSentTime: true },
    },
    {
        id: 'rojo',
        icon: '🔴',
        accent: '#dc2626',
        title: 'Envíos Masivos: Falta Algún Documento',
        description: 'Notifica a los clientes cuyo proceso está detenido por documentos faltantes. Se enviará el template <strong>estado_rojo</strong> con la lista completa de documentos requeridos.',
        templateName: 'estado_rojo',
        fetchEndpoint: '/admin/api/pending-falta-documento',
        sendEndpoint: '/admin/api/trigger-bulk-rojo',
        confirm: n => `¿Estás seguro de enviar el template "estado_rojo" a ${n} clientes seleccionados?`,
        executeLabel: '🔴 Ejecutar Envío a Seleccionados',
        batchSize: 15,
        features: { empresa: true, soloNuevos: true, finca: true, lastSentTime: true },
    },
    {
        id: 'amarillo',
        icon: '🟡',
        accent: '#d97706',
        title: 'Envíos Masivos: Listo en PandaDoc',
        description: 'Notifica a los clientes cuya solicitud está lista en PandaDoc para solicitar su número de cuenta. Se enviará el template <strong>estado_amarillo</strong>.',
        templateName: 'estado_amarillo',
        fetchEndpoint: '/admin/api/pending-listo-docusign',
        sendEndpoint: '/admin/api/trigger-bulk-amarillo',
        confirm: n => `¿Estás seguro de enviar el template "estado_amarillo" a ${n} clientes seleccionados?`,
        executeLabel: '🟡 Ejecutar Envío a Seleccionados',
        batchSize: 15,
        features: { empresa: true, soloNuevos: true, lastSentTime: true },
    },
    {
        id: 'negados',
        icon: '🚫',
        accent: '#6b7280',
        title: 'Envíos Masivos: Créditos Negados',
        description: 'Notifica a los clientes con solicitud en estado <strong>DENEGADO</strong> o <strong>CANCELADO POR LA EMPRESA</strong>. Se enviará el template <strong>estado_negados</strong>. Cada cliente solo recibe esta notificación <strong>una vez</strong>.',
        templateName: 'estado_negados',
        fetchEndpoint: '/admin/api/pending-denegado',
        sendEndpoint: '/admin/api/trigger-bulk-denegado',
        confirm: n => `¿Estás seguro de enviar el template "estado_negados" a ${n} cliente(s) seleccionado(s)?\n\nRecuerda: cada cliente solo debería recibir esta notificación una vez.`,
        executeLabel: '🚫 Enviar a Seleccionados',
        batchSize: 20,
        emptyMsg: 'No hay clientes pendientes por notificar.',
        features: { empresa: true, fechaSolicitud: true },
    },
    {
        id: 'actualizacion',
        icon: '📝',
        accent: '#9333ea',
        title: 'Envíos Masivos: Actualización Anual de Datos',
        description: 'Notifica a los clientes con préstamo <strong>activo</strong> que no han actualizado sus datos de contacto en los últimos 12 meses. Se enviará el template <strong>actualizacion_datos</strong>, que abre el flujo conversacional para que el cliente confirme cédula, teléfonos, dirección, correo y referencia personal.',
        templateName: 'actualizacion_datos',
        fetchEndpoint: '/admin/api/pending-actualizacion-datos',
        sendEndpoint: '/admin/api/trigger-bulk-actualizacion-datos',
        confirm: n => `¿Enviar el template "actualizacion_datos" a ${n} cliente(s)?\n\nEl cliente verá el bloque legal con la cita contractual y dos botones (Actualizar ahora / Más tarde).`,
        executeLabel: '📝 Enviar a Seleccionados',
        batchSize: 20,
        emptyMsg: 'No hay clientes pendientes por notificar.',
        features: {},
    },
].forEach(cfg => {
    const panel = createCampaignPanel(cfg);
    if (panel) CampaignPanels[cfg.id] = panel;
});
