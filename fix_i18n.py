import re

with open('lib/i18n.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# EN nav keys
en_nav = '''
    "nav.history": "History",
    "nav.adminDashboard": "Dashboard",
    "nav.traces": "Traces",
    "nav.ragEvidence": "RAG Evidence",
    "nav.consumerPreview": "Consumer Preview",
'''

# EN app keys
en_app = '''
    "app.loading": "Loading...",
    "app.redirecting": "Redirecting...",
    "app.accessDenied": "Access Denied",
    "app.adminName": "Admin Console",
    "app.consumerName": "AI Shopping Agent",
'''

# EN auth keys
en_auth = '''
    "auth.logout": "Logout",
    "auth.backToAdmin": "Back to Admin",
'''

# EN admin keys
en_admin = '''
    "admin.totalConversations": "Total Conversations",
    "admin.productSearches": "Product Searches",
    "admin.recommendationsGenerated": "Recommendations",
    "admin.ordersCreated": "Orders Created",
    "admin.checkoutConversion": "Checkout Rate",
    "admin.retrievalHitRate": "Retrieval Hit Rate",
    "admin.errorCount": "Error Count",
    "admin.userQuery": "User Query",
    "admin.error": "Error",
    "admin.recentActivity": "Recent Activity",
    "admin.technicalConsole": "Technical Console",
    "admin.sessionId": "Session ID",
    "admin.fallback": "Fallback",
    "admin.fallbackReason": "Fallback Reason",
    "admin.traceList": "Trace List",
    "admin.traceDetail": "Trace Detail",
    "admin.rawJson": "Raw JSON",
    "admin.response": "Response",
'''

en_intent = '''
    "intent.intent": "Intent",
'''

# EN insertions
content = content.replace('"nav.evaluation": "Evaluation",', '"nav.evaluation": "Evaluation",' + en_nav)
content = content.replace('"app.subtitle": "Mock-safe RAG, Agent, Payment and Evaluation",', '"app.subtitle": "Mock-safe RAG, Agent, Payment and Evaluation",' + en_app)
content = content.replace('"chat.copyFailed": "Copy failed"', '"chat.copyFailed": "Copy failed"' + en_auth)
content = content.replace('"products.outOfStock": "Out of Stock"', '"products.outOfStock": "Out of Stock"' + en_admin)
content = content.replace('"admin.response": "Response"', '"admin.response": "Response"' + en_intent)

# ZH nav keys
zh_nav = '''
    "nav.history": "历史记录",
    "nav.adminDashboard": "管理后台",
    "nav.traces": "Trace 详情",
    "nav.ragEvidence": "RAG 证据",
    "nav.consumerPreview": "消费者预览",
'''

zh_app = '''
    "app.loading": "加载中...",
    "app.redirecting": "重定向中...",
    "app.accessDenied": "访问被拒绝",
    "app.adminName": "管理控制台",
    "app.consumerName": "智能采购助手",
'''

zh_auth = '''
    "auth.logout": "退出登录",
    "auth.backToAdmin": "返回管理后台",
'''

zh_admin = '''
    "admin.totalConversations": "总请求数",
    "admin.productSearches": "搜索次数",
    "admin.recommendationsGenerated": "推荐次数",
    "admin.ordersCreated": "已创建订单",
    "admin.checkoutConversion": "下单转化率",
    "admin.retrievalHitRate": "检索命中率",
    "admin.errorCount": "错误数",
    "admin.userQuery": "用户输入",
    "admin.error": "错误信息",
    "admin.recentActivity": "最近活动",
    "admin.technicalConsole": "技术控制台",
    "admin.sessionId": "会话 ID",
    "admin.fallback": "降级",
    "admin.fallbackReason": "降级原因",
    "admin.traceList": "Trace 列表",
    "admin.traceDetail": "Trace 详情",
    "admin.rawJson": "原始 JSON",
    "admin.response": "响应",
'''

zh_intent = '''
    "intent.intent": "意图",
'''

content = content.replace('"nav.evaluation": "评估",', '"nav.evaluation": "评估",' + zh_nav)
content = content.replace('"app.subtitle": "Mock安全的RAG、Agent、支付与评估",', '"app.subtitle": "Mock安全的RAG、Agent、支付与评估",' + zh_app)
content = content.replace('"chat.copyFailed": "复制失败"', '"chat.copyFailed": "复制失败"' + zh_auth)
content = content.replace('"products.outOfStock": "库存不足"', '"products.outOfStock": "库存不足"' + zh_admin)
content = content.replace('"admin.response": "响应"', '"admin.response": "响应"' + zh_intent)

# FR nav keys
fr_nav = '''
    "nav.history": "Historique",
    "nav.adminDashboard": "Tableau de bord",
    "nav.traces": "Traces",
    "nav.ragEvidence": "Preuves RAG",
    "nav.consumerPreview": "Aperçu consommateur",
'''

fr_app = '''
    "app.loading": "Chargement...",
    "app.redirecting": "Redirection...",
    "app.accessDenied": "Accès refusé",
    "app.adminName": "Console d\\'administration",
    "app.consumerName": "Agent d\\'achat IA",
'''

fr_auth = '''
    "auth.logout": "Déconnexion",
    "auth.backToAdmin": "Retour à l\\'admin",
'''

fr_admin = '''
    "admin.totalConversations": "Total conversations",
    "admin.productSearches": "Recherches produits",
    "admin.recommendationsGenerated": "Recommandations",
    "admin.ordersCreated": "Commandes créées",
    "admin.checkoutConversion": "Taux de conversion",
    "admin.retrievalHitRate": "Taux de succès de recherche",
    "admin.errorCount": "Nombre d\\'erreurs",
    "admin.userQuery": "Requête utilisateur",
    "admin.error": "Erreur",
    "admin.recentActivity": "Activité récente",
    "admin.technicalConsole": "Console technique",
    "admin.sessionId": "ID de session",
    "admin.fallback": "Fallback",
    "admin.fallbackReason": "Raison du fallback",
    "admin.traceList": "Liste des traces",
    "admin.traceDetail": "Détail de trace",
    "admin.rawJson": "JSON brut",
    "admin.response": "Réponse",
'''

fr_intent = '''
    "intent.intent": "Intention",
'''

content = content.replace('"nav.evaluation": "Évaluation",', '"nav.evaluation": "Évaluation",' + fr_nav)
content = content.replace('"app.subtitle": "RAG, Agent, Paiement et Évaluation mock-safe",', '"app.subtitle": "RAG, Agent, Paiement et Évaluation mock-safe",' + fr_app)
content = content.replace('"chat.copyFailed": "Échec de copie"', '"chat.copyFailed": "Échec de copie"' + fr_auth)
content = content.replace('"products.outOfStock": "En rupture"', '"products.outOfStock": "En rupture"' + fr_admin)
content = content.replace('"admin.response": "Réponse"', '"admin.response": "Réponse"' + fr_intent)

with open('lib/i18n.tsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done - i18n keys added to all languages")
