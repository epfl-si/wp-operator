<?php

class EPFLTequilaPlugin extends Plugin
{
	protected $pluginPath = "tequila/EPFL-Tequila.php";
	private $plugin_epfl_tequila_has_dual_auth = 0;

	public function updateOptions()
	{
		update_option( 'plugin:epfl_tequila:has_dual_auth', $this->plugin_epfl_tequila_has_dual_auth);
	}
}
