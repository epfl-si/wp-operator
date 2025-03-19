"use strict";
const fs = require('fs');
const { exec } = require('child_process');

const namespace = "svc0041t-wordpress";
const patchFile = 'scripts/pluginPatch.sh';

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

function write(filePath, content) {
	fs.appendFile(filePath, content, (err) => {
		if (err) throw err;
	});
}

function makeFileExecutable() {
	fs.chmod(patchFile, 0o755, (err) => {
		if (err) throw err;
		console.log('Permissions changed successfully!');
	});

}

const run = async () => {
	const command = `kubectl get wps -n ${namespace} -o json | jq '[.items[]]'`;
	const wps = await execKubectl(command);
	for (const site of wps) {
		const pluginsArray = site.spec.wordpress.plugins || [];

		if (Array.isArray(pluginsArray)) {
			const plugins = pluginsArray.map(p => `${p}: {}`).join(',');
			write(patchFile,`kubectl patch WordpressSite ${site.metadata.name} -n ${namespace} --type='merge' -p '{"spec":{"wordpress":{"plugins":{${plugins}}}}}' \n`)
		}
	}
	makeFileExecutable();
}

run();
