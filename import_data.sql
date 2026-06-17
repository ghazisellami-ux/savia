-- Import only: utilisateurs, clients, equipements
-- Safe to run on existing database

DELETE FROM utilisateurs WHERE id > 1;
DELETE FROM clients;
DELETE FROM equipements;
COPY public.utilisateurs (id, username, password_hash, nom_complet, role, client, email, actif, created_at, last_login, profil, pages_autorisees) FROM stdin;
40	admin	\\\\\\.
COPY public.clients (id, nom, matricule_fiscale, ville, contact, telephone, adresse, date_creation, code_client, region, type_client, international) FROM stdin;
201	clinique du lac	1111111	Tunis	Dr Ali	52416398	rue du lac	2026-06-15 13:28:20.53068	CL001	Nord	Priv├®	f
202	clinique avicenne	222222	Mahdia	Dr Ahmed	56514287	rue du m├®decin	2026-06-15 13:29:17.09069	CL002	Centre	Priv├®	f
203	Clinique du parc	33333	Sfax	Dr Samir	74512689	rue du parc	2026-06-15 14:06:13.208752	CL003	Sud	Priv├®	f
\.
COPY public.equipements (id, nom, type, fabricant, modele, num_serie, date_installation, derniere_maintenance, statut, notes, client, domaine, est_annexe, garantie_debut, garantie_duree, matricule_fiscale, document_technique, latitude, longitude, adresse, ville, region, service) FROM stdin;
502	Scanner 16B	Scanner CT	Canon	Acquillion	sn45874	2026-06-15	2026-06-15	Op├®rationnel		clinique avicenne	Radiologie	f	2026-06-15	4	222222		\N	\N		Mahdia	Centre	Radiologie
503	IRM 3T	IRM	GE Healthcare	Signa	sn12345	2026-06-15	2026-06-15	Op├®rationnel		clinique avicenne	Radiologie	f	2026-06-15	5	222222		\N	\N		Mahdia	Centre	Radiologie
504	Table t├®l├®command├®e	Fluoroscopie	Philips	Optima	sn 14587	2026-06-15	2026-06-15	Op├®rationnel		clinique du lac	Radiologie	f	2026-06-15	2	1111111		\N	\N		Tunis	Nord	Radiologie
505	Echographe 4S	├ëchographe	Esaote	premium 2	sn7548	2026-06-15	2026-06-15	Op├®rationnel		clinique du lac	Ultrason	f	2026-06-15	1	1111111		\N	\N		Tunis	Nord	Radiologie
506	Mammographe 	Mammographie	Fujifilm	OP200	sn45730	2026-06-15	2026-06-15	Op├®rationnel		clinique avicenne	Radiologie	f	2026-06-15	1	222222		\N	\N		Mahdia	Centre	Radiologie
507	Scanner 32B	Scanner CT	Fujifilm	Scenaria	SN621487	2026-06-15	2026-06-15	Op├®rationnel		clinique du lac	Radiologie	f	2026-06-18	4	1111111		\N	\N		Tunis	Nord	Radiologie
508	Cone beam	Cone beam	Medtronic	OC100	sn76128	2026-06-15	2026-06-15	Op├®rationnel		clinique avicenne	Radiologie	f	2026-06-30	1	222222		\N	\N		Mahdia	Centre	Radiologie
509	Scanner 128B	Scanner CT	Fujifilm	Supria	sn74459	2026-06-15	2026-06-15	Op├®rationnel		Clinique du parc	Radiologie	f	2026-06-22	4	33333		\N	\N		Sfax	Sud	Radiologie
\.

