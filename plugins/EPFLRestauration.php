<?php

class EPFLRestaurationPlugin extends Plugin
{
	protected $pluginPath = "epfl-restauration/epfl-restauration.php";
	private $epfl_restauration_api_username = 'epfl.getmenu@nutrimenu.ch';
	private $epfl_restauration_api_url = 'https://nutrimenu.ch/nmapi/getMenu';

	private function epfl_restauration_api_password() {
		return $this->getSecretValue('restauration_api_password');
	}

	public function updateOptions()
	{
		update_option( 'epfl_restauration_api_username', $this->epfl_restauration_api_username);
		update_option( 'epfl_restauration_api_url', $this->epfl_restauration_api_url);
		update_option( 'epfl_restauration_api_password', $this->epfl_restauration_api_password());
	}
}
