import { mount } from 'svelte';
import App from './app/App.svelte';
import './styles/tokens.css';
import './styles/base.css';

const target = document.getElementById('app');
if (!target) throw new Error('#app mount point missing');

export default mount(App, { target });
