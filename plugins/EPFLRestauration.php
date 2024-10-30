<?php

class EPFLRestauration extends Plugin
{
	protected $pluginPath = "epfl-restauration/epfl-restauration.php";
	private $epfl_restauration_api_username = 'epfl.getmenu@nutrimenu.ch';
	private $epfl_restauration_api_url = 'https://nutrimenu.ch/nmapi/getMenu';
	private $epfl_restauration_api_password = 'XXX';

	public function updateOptions()
	{
		foreach (get_object_vars($this) as $property => $value) {
			update_option( $property, $value );
		}
	}

	public function getPluginPath(): string
	{
		return this->$pluginPath;
	}
}
