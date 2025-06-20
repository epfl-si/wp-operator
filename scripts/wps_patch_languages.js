"use strict";
const { promises: fs } = require("fs");
const { exec } = require('child_process');

const namespace = "wordpress-test";
const patchFile = 'scripts/patchlanguages.sh';

async function execKubectl(command) {
	return new Promise((resolve, reject) => {
		exec(command, (error, stdout, stderr) => {
			if (error) {
				reject(`Error executing command: ${error.message}`);
				return;
			}
			if (stderr) {
				reject(`Error output: ${stderr}`);
				return;
			}
			resolve(JSON.parse(stdout));
		});
	});
}

async function write(content) {
	await fs.writeFile(patchFile, content);
}

async function makeFileExecutable() {
	await fs.chmod(patchFile, 0o755);
}

const LANGUAGES = [
	{ name: "English", locale: "en_US", rtl: 0, term_group: 0, flag: "us", slug: "en_US" },
	{ name: "English", locale: "en_GB", rtl: 0, term_group: 29, flag: "gb", slug: "en_GB" },
	{ name: "Français", locale: "fr_FR", rtl: 0, term_group: 1, flag: "fr", slug: "fr_FR" },
	{ name: "Deutsch", locale: "de_CH", rtl: 0, term_group: 20, flag: "ch", slug: "de_CH" },
	{ name: "Deutsch", locale: "de_CH_informal", rtl: 0, term_group: 21, flag: "ch", slug: "de_CH_informal" },
	{ name: "Deutsch", locale: "de_DE", rtl: 0, term_group: 22, flag: "de", slug: "de_DE" },
	{ name: "Українська", locale: "uk", rtl: 0, term_group: 128, flag: "ua", slug: "uk" },
	{ name: "Italiano", locale: "it_IT", rtl: 0, term_group: 3, flag: "it", slug: "it_IT" },
	{ name: "Español", locale: "es_ES", rtl: 0, term_group: 4, flag: "es", slug: "es_ES" },
	{ name: "Ελληνικά", locale: "el", rtl: 0, term_group: 5, flag: "gr", slug: "el" },
	{ name: "Română", locale: "ro_RO", rtl: 0, term_group: 6, flag: "ro", slug: "ro_RO" },
	{ name: "فارسی", locale: "fa_IR", rtl: 1, term_group: 50, flag: "ir", slug: "fa_IR" },
	{ name: "Polski", locale: "pl_PL", rtl: 0, term_group: 97, flag: "pl", slug: "pl_PL" },
];

const run = async () => {
	const command = `kubectl get wps -n ${namespace} -o json | jq '[.items[] | {NAME: .metadata.name, languages: .status.wordpresssite.languages, polylang_spec: .spec.wordpress.plugins.polylang.polylang}]'`;
	const wps = await execKubectl(command);
	for (const site of wps) {
		if (site["polylang_spec"] != null)
			continue;
		const languageList = []
		site["languages"].forEach(l => {
			languageList.push(LANGUAGES.find(lang => lang.locale == l))
		})
		await write(`kubectl patch wp ${site.NAME} -n ${namespace} --type='merge' -p '{"spec":{"wordpress": {"plugins": {"polylang": {"polylang": {"languages": ${JSON.stringify(languageList)}}}}}}}' \n`)
		await makeFileExecutable();
	}
}

run();
