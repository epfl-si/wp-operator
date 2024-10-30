<?php
abstract class Plugin {
	protected $pluginPath;

	protected function __construct() {

	}

	public static function create($type) {
		switch ($type) {
			case 'Polylang':
				return new Polylang();
			case 'Restauration':
				return new EPFLRestauration();
			default:
				throw new Exception("Unknown plugin type");
		}
	}

	abstract public function updateOptions();
	abstract public function getPluginPath(): string;
}
