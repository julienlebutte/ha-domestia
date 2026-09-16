# Domestia pour Home Assistant

Intégration Home Assistant native pour un contrôleur d'éclairage **Domestia DMC-008** :
communication directe en TCP avec le contrôleur (aucun bridge externe, aucun broker MQTT
requis), configuration entièrement depuis l'interface Home Assistant, et découverte
automatique des relais.

Réimplémentation Python du protocole utilisé par le projet Go
[go-domestia](https://github.com/victorjacobs/go-domestia) (désormais archivé).

## Fonctionnalités

- Ajout et configuration 100% via l'UI Home Assistant (aucun YAML)
- Découverte automatique du nombre de relais gérés par le contrôleur
- Une entité `light` créée par relais, avec un nom générique (`Domestia relay N`) tant
  qu'il n'est pas personnalisé
- Écran **Configurer** pour renommer un relais, le passer en variateur (`dimmable`) ou le
  marquer "toujours allumé" (non exposé comme entité, mais maintenu à pleine luminosité)
- Un seul polling groupé (une requête réseau) pour l'ensemble des relais, quel que soit
  leur nombre (testé avec ~30 relais)

## Installation via HACS

1. Dans HACS, menu ⋮ → **Dépôts personnalisés** → ajoute l'URL de ce dépôt, catégorie
   *Intégration*.
2. Recherche "Domestia" dans HACS → **Télécharger**.
3. Redémarre Home Assistant.
4. **Paramètres → Appareils et services → Ajouter une intégration → Domestia**, renseigne
   l'adresse IP du contrôleur.

## Installation manuelle

Copie le dossier `custom_components/domestia` de ce dépôt dans
`<config Home Assistant>/custom_components/`, redémarre HA, puis ajoute l'intégration
comme ci-dessus.

## Configuration

Aucun YAML n'est nécessaire. Après l'ajout de l'intégration, le bouton **Configurer** sur
sa carte (Paramètres → Appareils et services) permet de :

- choisir la fréquence de rafraîchissement (par défaut 10 secondes)
- éditer un relais précis : nom affiché, variateur ou non (`dimmable`), toujours-allumé
  (`always_on`)

Les relais non personnalisés restent visibles avec leur nom générique et un
comportement par défaut **non-dimmable** (simple on/off) et pas toujours-allumé — active
`dimmable` sur les relais qui le supportent réellement.

## Licence

Voir [LICENSE](LICENSE).

## Acknowledgments

This project is a Python reimplementation of the Domestia DMC-008 wire protocol
originally reverse-engineered in Go by **Victor Jacobs** in
[go-domestia](https://github.com/victorjacobs/go-domestia) (now archived). His work
figuring out the controller's binary framing and command bytes made this Home Assistant
integration possible — thank you for documenting it. This repository carries no code
copied from that project (its own repository has no LICENSE file to reuse); only the
protocol knowledge was carried over, reimplemented independently in Python.
