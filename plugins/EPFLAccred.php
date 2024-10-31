<?php

class EPFLAccred extends Plugin
{
	protected $pluginPath = "accred/EPFL-Accred.php";
	private $plugin_epfl_accred_administrator_group = "{{ wp_administrator_group }}";
	private $plugin_epfl_accred_unit = "{{ wp_unit_name }}";
	private $plugin_epfl_accred_unit_id = "{{ wp_unit_id }}";

	public function updateOptions()
	{
		update_option( 'plugin:epfl_accred:administrator_group', $this->plugin_epfl_accred_administrator_group);
		update_option( 'plugin:epfl_accred:unit', $this->plugin_epfl_accred_unit);
		update_option( 'plugin:epfl_accred:unit_id', $this->plugin_epfl_accred_unit_id);
	}
}
